"""Session management commands: /history, /session, /stats."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from haney.commands._state import get_session_manager


def cmd_history(console: Console, args: list[str]) -> None:
    """Show recent sessions (historical records only — not loaded)."""
    from haney.session_manager import SessionManager
    sessions = SessionManager.list_sessions()

    if not sessions:
        console.print("[dim]No previous sessions found.[/dim]")
        return

    table = Table(
        title=f"Recent Sessions ({len(sessions)} total)",
        border_style="blue",
        title_justify="left",
    )
    table.add_column("Session ID", style="bold cyan", no_wrap=True)
    table.add_column("Provider", style="dim")
    table.add_column("Model", style="dim")
    table.add_column("Msgs", justify="right")
    table.add_column("Cost", justify="right")

    for s in sessions[:20]:
        table.add_row(
            s["session_id"],
            s["provider"],
            s["model"],
            str(s["messages"]),
            f"${s['cost']:.4f}",
        )

    console.print(table)
    console.print("[dim]Sessions are historical records only — not loaded into context.[/dim]")


def cmd_session(console: Console, args: list[str]) -> None:
    """Display current session information."""
    mgr = get_session_manager()
    if mgr is None:
        console.print("[yellow]No active session.[/yellow]")
        return

    table = Table(
        title=f"Current Session — {mgr.session_id}",
        border_style="green",
        title_justify="left",
    )
    table.add_column("Setting", style="bold", no_wrap=True)
    table.add_column("Value", style="cyan")

    table.add_row("Session ID", mgr.session_id)
    table.add_row("Provider", mgr.provider)
    table.add_row("Model", mgr.model)
    table.add_row("Started", mgr.started_at_display)
    table.add_row("Messages", str(mgr.message_count))
    table.add_row("API Calls", str(mgr.api_calls))
    table.add_row("Input Tokens", f"{mgr.input_tokens:,}")
    table.add_row("Output Tokens", f"{mgr.output_tokens:,}")
    table.add_row("Total Tokens", f"{mgr.total_tokens:,}")
    table.add_row("Cost", f"${mgr.cost:.4f}")
    if mgr.context_tokens:
        table.add_row("Context Size", f"~{mgr.context_tokens:,} tokens")

    console.print(table)


def cmd_stats(console: Console, args: list[str]) -> None:
    """Display token and cost metrics for the current session."""
    mgr = get_session_manager()
    if mgr is None:
        console.print("[yellow]No active session.[/yellow]")
        return

    table = Table(
        title="Session Stats",
        border_style="cyan",
        title_justify="left",
    )
    table.add_column("Metric", style="bold", no_wrap=True)
    table.add_column("Value", style="cyan", justify="right")

    table.add_row("Input Tokens", f"{mgr.input_tokens:,}")
    table.add_row("Output Tokens", f"{mgr.output_tokens:,}")
    table.add_row("Total Tokens", f"{mgr.total_tokens:,}")
    table.add_row("API Calls", str(mgr.api_calls))
    table.add_row("Cost", f"${mgr.cost:.4f}")

    if mgr.api_calls > 0:
        avg_in = mgr.input_tokens // mgr.api_calls
        avg_out = mgr.output_tokens // mgr.api_calls
        table.add_section()
        table.add_row("Avg Input/Call", f"{avg_in:,}")
        table.add_row("Avg Output/Call", f"{avg_out:,}")

    console.print(table)
