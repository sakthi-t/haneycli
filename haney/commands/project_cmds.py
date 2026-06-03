"""Project awareness commands: /project, /reload, /context, /init."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from haney.commands._state import get_context_manager


def cmd_project(console: Console, args: list[str]) -> None:
    """Display current project information.

    Shows project name, awareness status, loaded/missing files,
    context size, and last reload time. Never fails.
    """
    ctx = get_context_manager()
    high = ctx.high_priority_files
    missing = ctx.missing_awareness_files
    all_loaded = ctx.loaded_files
    tokens = ctx.total_tokens
    ago = ctx.last_reload_seconds

    table = Table(
        title=f"Project Status — {ctx.project_name}",
        border_style="green" if ctx.has_any_awareness else "yellow",
        title_justify="left",
    )
    table.add_column("Setting", style="bold", no_wrap=True)
    table.add_column("Value", style="cyan")

    table.add_row("Project Name", ctx.project_name)
    table.add_row(
        "Project Awareness",
        "[green]Enabled[/green]" if ctx.has_any_awareness else "[yellow]Limited[/yellow]",
    )
    table.add_row(
        "Context Size",
        f"~{tokens} tokens" if tokens else "[dim]empty[/dim]",
    )

    if ago < 60:
        ago_str = f"{ago:.0f}s ago"
    elif ago < 3600:
        ago_str = f"{ago / 60:.0f}m ago"
    else:
        ago_str = f"{ago / 3600:.1f}h ago"
    table.add_row("Last Reload", ago_str)

    console.print(table)

    if high:
        console.print("\n[bold]Loaded Files:[/bold]")
        for f in high:
            kb = f.size_bytes / 1024
            console.print(f"  [green]✓[/green] {f.name} [dim]({kb:.1f} KB)[/dim]")

    if missing:
        console.print("\n[bold yellow]Missing Files:[/bold yellow]")
        for name in missing:
            console.print(f"  [yellow]⚠[/yellow] {name}")
        if missing and not high:
            console.print("\n[dim]Suggestion: Run /init to generate project files.[/dim]")

    sources = [f for f in all_loaded if f.priority == "source"]
    if sources:
        console.print(f"\n[bold]Detected Source Files:[/bold] [dim]({len(sources)} files)[/dim]")
        shown = sources[:8]
        for f in shown:
            console.print(f"  [dim]  {f.name}[/dim]")
        if len(sources) > 8:
            console.print(f"  [dim]  … and {len(sources) - 8} more[/dim]")

    if not high and not sources:
        console.print("\n[dim]No project files detected. Run /init to create awareness files.[/dim]")


def cmd_reload(console: Console, args: list[str]) -> None:
    """Re-scan and reload all project files.

    Refreshes internal context, recalculates token estimates,
    and updates the file cache.
    """
    console.print("[bold]Reloading project…[/bold]\n")

    ctx = get_context_manager()
    ctx.reload()

    high = ctx.high_priority_files
    missing = ctx.missing_awareness_files

    for f in high:
        console.print(f"  [green]✓[/green] {f.name}")

    for name in missing:
        console.print(f"  [yellow]⚠[/yellow] {name} [dim](not found)[/dim]")

    if not high and not missing:
        console.print("  [dim]No project awareness files found.[/dim]")

    tokens = ctx.total_tokens
    console.print(f"\n[bold green]Project context refreshed.[/bold green]")
    if tokens:
        console.print(f"[dim]Context size: ~{tokens} tokens[/dim]")


def cmd_context(console: Console, args: list[str]) -> None:
    """Display loaded context details with token estimates.

    Shows file sizes, token counts, and overall context health.
    """
    ctx = get_context_manager()
    all_loaded = ctx.loaded_files

    if not all_loaded:
        console.print("[yellow]No project files loaded.[/yellow]")
        console.print("[dim]Run /init to create awareness files, then /reload to scan.[/dim]")
        return

    table = Table(
        title=f"Loaded Context — {ctx.project_name}",
        border_style="blue",
        title_justify="left",
    )
    table.add_column("File", style="bold cyan", no_wrap=True)
    table.add_column("Size", style="dim", justify="right")
    table.add_column("Est. Tokens", style="dim", justify="right")
    table.add_column("Priority", style="dim")

    total_size = 0
    total_tokens = 0

    for f in all_loaded:
        kb = f.size_bytes / 1024
        tokens = ctx.estimate_tokens(f.content)
        total_size += f.size_bytes
        total_tokens += tokens
        prio_label = {
            "high": "[green]high[/green]",
            "medium": "[yellow]medium[/yellow]",
            "source": "[dim]source[/dim]",
        }.get(f.priority, f.priority)
        table.add_row(f.name, f"{kb:.1f} KB", str(tokens), prio_label)

    table.add_section()
    table.add_row(
        "[bold]Total[/bold]",
        f"[bold]{total_size / 1024:.1f} KB[/bold]",
        f"[bold]{total_tokens}[/bold]",
        "",
    )

    console.print(table)

    if total_tokens < 4000:
        health = "[green]Healthy[/green]"
    elif total_tokens < 8000:
        health = "[yellow]Moderate[/yellow]"
    else:
        health = "[red]Large — consider /compact[/red]"

    console.print(f"\nContext Status: {health}")


def cmd_init(console: Console, args: list[str]) -> None:
    """Generate starter project-awareness files.

    Creates plan.md, memory.md, summary.md, and tasks.md.
    Only creates files that do not already exist — never
    overwrites user content.
    """
    ctx = get_context_manager()
    created = ctx.init_files()

    if not created:
        console.print("[yellow]All project-awareness files already exist.[/yellow]")
        console.print("[dim]Nothing to create. Files present:[/dim]")
        for f in ctx.high_priority_files:
            console.print(f"  [green]✓[/green] {f.name}")
        return

    for name in created:
        console.print(f"  [green]✓[/green] Created {name}")

    console.print(f"\n[dim]Project files created in {ctx.cwd}/[/dim]")
    console.print("[dim]Run /reload to load them into context.[/dim]")
