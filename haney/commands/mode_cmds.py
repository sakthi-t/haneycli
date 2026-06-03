"""Mode, thinking, and permission commands: /think, /status, /plan, /edit, /mode, /permission."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from haney.providers import (
    get_active_provider,
    get_active_model,
    is_web_search_enabled,
)
from haney.thinking_manager import (
    get_thinking_mode,
    set_thinking_mode,
)
from haney.mode_manager import get_mode, set_mode
from haney.permission_manager import (
    get_permission_mode,
    PermissionManager,
)
from haney.commands._state import get_session_manager, get_perm_manager


def cmd_think(console: Console, args: list[str]) -> None:
    """Show or set the thinking mode.

    Usage:
        /think              — Show current thinking config
        /think off          — Disable enhanced reasoning
        /think low          — Low reasoning effort
        /think medium       — Medium (default)
        /think high         — High / extended reasoning
    """
    if not args:
        provider = get_active_provider() or "?"
        model = get_active_model() or "?"
        think = get_thinking_mode()

        table = Table(
            title="Thinking Configuration",
            border_style="magenta",
            title_justify="left",
        )
        table.add_column("Setting", style="bold", no_wrap=True)
        table.add_column("Value", style="cyan")
        table.add_row("Mode", think)
        table.add_row("Provider", provider)
        table.add_row("Model", model)
        console.print(table)
        console.print("\n[dim]Usage: /think off|low|medium|high[/dim]")
        return

    mode = args[0].lower().strip()
    try:
        set_thinking_mode(mode)
        label = mode.upper() if mode != "off" else "OFF"
        console.print(f"[bold green]✓[/bold green] Thinking mode set to [bold]{label}[/bold]")
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")


def cmd_status(console: Console, args: list[str]) -> None:
    """Display current runtime status with all metrics."""
    provider = get_active_provider() or "not set"
    model = get_active_model() or "not set"
    think = get_thinking_mode()
    search_on = is_web_search_enabled()

    table = Table(
        title="Haney Status",
        border_style="cyan",
        title_justify="left",
    )
    table.add_column("Setting", style="bold", no_wrap=True)
    table.add_column("Value", style="cyan")

    table.add_row("Provider", provider)
    table.add_row("Model", model)
    table.add_row("Thinking", think)
    table.add_row("Search", "[green]Enabled[/green]" if search_on else "[yellow]Disabled[/yellow]")
    table.add_row("Mode", "[bold green]EDIT[/bold green]" if get_mode() == "edit" else "[bold cyan]PLAN[/bold cyan]")

    mgr = get_session_manager()
    if mgr is not None:
        table.add_section()
        table.add_row("Session Cost", f"${mgr.cost:.4f}")
        table.add_row("Input Tokens", f"{mgr.input_tokens:,}")
        table.add_row("Output Tokens", f"{mgr.output_tokens:,}")
        table.add_row("Total Tokens", f"{mgr.total_tokens:,}")
        table.add_row("API Calls", str(mgr.api_calls))
        table.add_row("Messages", str(mgr.message_count))

    if mgr is not None and mgr.context_tokens:
        table.add_row("Context Size", f"~{mgr.context_tokens:,} tokens")

    console.print(table)


def cmd_plan(console: Console, args: list[str]) -> None:
    """Switch to PLAN mode. Blocks tool execution."""
    set_mode("plan")
    console.print("[bold cyan]Mode changed to PLAN.[/bold cyan]")
    console.print("[dim]Tool execution disabled. Use /edit to allow modifications.[/dim]")


def cmd_edit(console: Console, args: list[str]) -> None:
    """Switch to EDIT mode. Enables tool execution."""
    set_mode("edit")
    console.print("[bold green]Mode changed to EDIT.[/bold green]")
    console.print("[dim]File operations enabled. Tool execution enabled.[/dim]")


def cmd_mode_show(console: Console, args: list[str]) -> None:
    """Display the current execution mode."""
    current = get_mode()

    table = Table(title="Current Mode", border_style="cyan", title_justify="left")
    table.add_column("Setting", style="bold", no_wrap=True)
    table.add_column("Value", style="cyan")

    if current == "edit":
        table.add_row("Mode", "[bold green]EDIT[/bold green]")
        table.add_row("Tool Execution", "[green]Enabled[/green]")
    else:
        table.add_row("Mode", "[bold cyan]PLAN[/bold cyan]")
        table.add_row("Tool Execution", "[yellow]Disabled[/yellow]")

    console.print(table)
    console.print("\n[dim]Use /plan or /edit to switch modes.[/dim]")


def cmd_permission(console: Console, args: list[str]) -> None:
    """Show or set permission mode.

    Usage:
        /permission          — Show current mode
        /permission ask      — Switch to ASK (prompt every time)
        /permission save     — Switch to SAVE (remember for session)
        /permission auto     — Switch to AUTO (auto-approve)
    """
    perm_mgr = get_perm_manager()

    if not args:
        current = get_permission_mode()
        table = Table(title="Permission Mode", border_style="yellow", title_justify="left")
        table.add_column("Setting", style="bold", no_wrap=True)
        table.add_column("Value", style="cyan")

        label = current.upper()
        if current == "auto":
            label = f"[bold red]{label}[/bold red]"
        elif current == "save":
            label = f"[bold yellow]{label}[/bold yellow]"
        table.add_row("Current", label)

        if current == "save" and perm_mgr.session_approvals:
            approved = ", ".join(sorted(perm_mgr.session_approvals))
            table.add_row("Session Approvals", approved)

        console.print(table)
        console.print("\n[dim]Usage: /permission ask | save | auto[/dim]")
        return

    mode = args[0].lower().strip()
    try:
        perm_mgr.set_mode(mode)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        return

    if mode == "save":
        console.print("[bold yellow]Permission mode: SAVE[/bold yellow]")
        console.print("[yellow]⚠ Approvals are remembered for the current session.[/yellow]")
    elif mode == "auto":
        console.print("[bold red]Permission mode: AUTO[/bold red]")
        console.print("[red]⚠ Haney may modify files without confirmation.[/red]")
    else:
        console.print("[bold green]Permission mode: ASK[/bold green]")
        console.print("[dim]Every modifying action requires confirmation.[/dim]")
