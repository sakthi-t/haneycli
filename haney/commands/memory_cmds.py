"""Memory & compact commands: /remember, /summary, /compact."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from haney.llm import ChatSession


def cmd_remember(console: Console, args: list[str]) -> None:
    """Append information to memory.md.

    Usage: /remember <text>
    """
    if not args:
        console.print("[yellow]Usage:[/yellow] /remember <information to save>")
        console.print("[dim]Example: /remember Use FastAPI for this project[/dim]")
        return

    text = " ".join(args).strip()
    memory_path = Path.cwd() / "memory.md"

    try:
        if memory_path.is_file():
            existing = memory_path.read_text(encoding="utf-8").rstrip()
            content = existing + "\n\n* " + text + "\n"
        else:
            content = "# Project Memory\n\n* " + text + "\n"

        memory_path.write_text(content, encoding="utf-8")
        console.print(f"[bold green]✓[/bold green] Added to [bold]memory.md[/bold]:")
        console.print(f"  [cyan]{text}[/cyan]")
        console.print("\n[dim]Run /reload to refresh project context.[/dim]")
    except OSError as exc:
        console.print(f"[red]Cannot write memory.md: {exc}[/red]")


def cmd_summary(console: Console, args: list[str]) -> None:
    """Display current summary.md content. No LLM call required."""
    summary_path = Path.cwd() / ".haney" / "summary.md"

    if not summary_path.is_file():
        console.print("[yellow]No summary available.[/yellow]")
        console.print("[dim]Run /compact to generate one.[/dim]")
        return

    try:
        content = summary_path.read_text(encoding="utf-8")
    except OSError:
        console.print("[red]Cannot read summary.md[/red]")
        return

    console.print(Panel(
        content.strip(),
        title="Project Summary",
        border_style="cyan",
        title_align="left",
    ))


def cmd_compact(console: Console, session: "ChatSession") -> None:
    """Compact conversation using an LLM call and update summary.md.

    Gathers conversation history, project context, and memory,
    sends to the active model for summarisation, writes to
    summary.md, and truncates old messages.

    Args:
        console: Rich Console instance.
        session: Active ChatSession for LLM call and message truncation.
    """
    import litellm
    from haney.providers import get_active_provider, get_api_key, get_active_model
    from haney.project_context import ProjectContextManager

    provider = get_active_provider()
    if not provider:
        console.print("[red]No active provider. Use /login first.[/red]")
        return

    model = get_active_model()
    if not model:
        console.print("[red]No active model. Use /model first.[/red]")
        return

    api_key = get_api_key(provider)
    if not api_key:
        console.print(f"[red]No API key for {provider}.[/red]")
        return

    ctx = ProjectContextManager()
    ctx.reload()

    memory = ""
    mem_path = Path.cwd() / "memory.md"
    if mem_path.is_file():
        memory = mem_path.read_text(encoding="utf-8")

    old_summary = ""
    sum_path = Path.cwd() / ".haney" / "summary.md"
    if sum_path.is_file():
        old_summary = sum_path.read_text(encoding="utf-8")

    conversation = ""
    for m in session.messages[-40:]:
        role = m.get("role", "?")
        content = m.get("content", "")[:1000]
        conversation += f"**{role}:** {content}\n\n"

    tokens_before = sum(len(m.get("content", "")) for m in session.messages) // 4

    console.print("[bold cyan]Compacting conversation…[/bold cyan]\n")

    prompt = f"""You are generating a concise project summary for Haney CLI.

## Project Memory
{memory if memory else '(none)'}

## Previous Summary
{old_summary if old_summary else '(none)'}

## Recent Conversation
{conversation}

---

Generate a concise project summary covering:
- Completed work
- Important decisions
- Current architecture
- Open tasks
- Known issues

Keep under 1000 words. Use Markdown."""

    try:
        response = litellm.completion(
            model=f"{provider}/{model}",
            messages=[{"role": "user", "content": prompt}],
            api_key=api_key,
        )
        summary_text = response.choices[0].message.content or ""
    except Exception as exc:
        console.print(f"[red]LLM call failed: {exc}[/red]")
        return

    try:
        sum_path.write_text(summary_text.strip(), encoding="utf-8")
        console.print("[green]✓[/green] [bold]summary.md updated[/bold]")
    except OSError as exc:
        console.print(f"[red]Cannot write summary.md: {exc}[/red]")
        return

    before_count = len(session.messages)
    if before_count > 20:
        session.messages = session.messages[-10:]
        after_count = len(session.messages)
    else:
        after_count = before_count

    ctx.reload()

    tokens_after = sum(len(m.get("content", "")) for m in session.messages) // 4
    if tokens_before > 0:
        reduction = int((1 - tokens_after / tokens_before) * 100)
    else:
        reduction = 0

    console.print()
    table = Table(title="Compact Results", border_style="green", title_justify="left")
    table.add_column("Metric", style="bold")
    table.add_column("Value", style="cyan", justify="right")
    table.add_row("Messages before", str(before_count))
    table.add_row("Messages after", str(after_count))
    table.add_row("Tokens before", f"~{tokens_before:,}")
    table.add_row("Tokens after", f"~{tokens_after:,}")
    table.add_row("Estimated reduction", f"{reduction}%")
    console.print(table)

    console.print("\n[dim]summary.md and memory.md are now injected into future context.[/dim]")
