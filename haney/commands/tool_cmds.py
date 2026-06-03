"""Trash & restore commands: /trash, /restore."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel


def cmd_trash(console: Console, args: list[str]) -> None:
    """Show files in .haney/trash/."""
    from haney.tools.file_tools import list_trash
    result = list_trash(Path.cwd())
    if result.success:
        console.print(Panel(
            result.content_preview or result.message,
            title="Trash",
            border_style="yellow",
            title_align="left",
        ))
        console.print("[dim]Use /restore <filename> to recover a file.[/dim]")
    else:
        console.print(f"[red]{result.message}[/red]")


def cmd_restore(console: Console, args: list[str]) -> None:
    """Restore a file from .haney/trash/.

    Usage: /restore <filename>
    """
    from haney.tools.file_tools import restore_file
    if not args:
        console.print("[yellow]Usage:[/yellow] /restore <filename>")
        console.print("[dim]Use /trash to see files available for restore.[/dim]")
        return

    filename = args[0].strip()
    result = restore_file(Path.cwd(), filename)
    if result.success:
        console.print(f"[bold green]✓[/bold green] {result.message}")
    else:
        console.print(f"[red]{result.message}[/red]")
