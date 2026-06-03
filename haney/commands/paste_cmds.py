"""Paste buffer commands: /pastes, /paste-compact."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from haney.providers import load_config, save_config
from haney.paste_buffer import get_paste_buffer


def cmd_pastes(console: Console, args: list[str]) -> None:
    """List or manage stored paste buffers.

    Usage:
        /pastes             — List all stored pastes
        /pastes clear       — Clear all stored pastes
        /pastes <id>        — Show full content of a paste

    Args:
        console: Rich Console instance for output.
        args: Command arguments (optional action).
    """
    buf = get_paste_buffer()

    if args and args[0].lower() == "clear":
        count = buf.count()
        buf.clear()
        console.print(f"[bold green]✓[/bold green] Cleared {count} stored paste(s).")
        return

    if args:
        label = args[0].strip()
        content = buf.get(label)
        if content is None:
            console.print(f"[red]Paste not found:[/red] {label}")
            console.print("[dim]Use /pastes to list all stored pastes.[/dim]")
            return
        console.print(f"[bold]Paste:[/bold] {label}")
        console.print(f"[dim]Length: {len(content)} chars, {len(content.splitlines())} lines[/dim]")
        console.print()
        console.print(content)
        return

    pastes = buf.get_all()
    if not pastes:
        console.print("[dim]No pastes stored. Paste large text in chat to compact it.[/dim]")
        return

    table = Table(title="Stored Pastes", border_style="green", title_justify="left")
    table.add_column("ID", style="bold cyan", no_wrap=True)
    table.add_column("Size", style="dim")
    table.add_column("Lines", style="dim")
    table.add_column("Preview", style="dim")

    for label, content in pastes.items():
        size = len(content)
        if size >= 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size} B"
        lines = len(content.split("\n"))
        preview = content[:80].replace("\n", "↵") + (
            "…" if len(content) > 80 else ""
        )
        table.add_row(label, size_str, str(lines), preview)

    console.print(table)
    console.print(
        "\n[dim]Use /pastes <id> to view full content. Use /pastes clear to remove all.[/dim]"
    )


def cmd_paste_compact(console: Console, args: list[str]) -> None:
    """Toggle compact paste display on or off.

    Usage:
        /paste-compact        — Show current setting
        /paste-compact on     — Enable compact display
        /paste-compact off    — Disable compact display

    When enabled, large or multi-line pastes are stored in a
    buffer and shown as compact [pasteN] labels instead of
    filling the terminal with pasted text.

    Args:
        console: Rich Console instance for output.
        args: Command arguments (optional on/off).
    """
    config = load_config()
    ui = config.get("ui", {})
    current = ui.get("paste_compact", True)

    if not args:
        status = "[green]on[/green]" if current else "[yellow]off[/yellow]"
        console.print(f"Paste compaction: {status}")
        return

    setting = args[0].lower().strip()
    if setting == "on":
        ui["paste_compact"] = True
        config["ui"] = ui
        save_config(config)
        console.print("[bold green]✓[/bold green] Paste compaction enabled.")
        console.print(
            "[dim]Large pastes will be stored as [pasteN] labels instead of flooding the terminal.[/dim]"
        )
    elif setting == "off":
        ui["paste_compact"] = False
        config["ui"] = ui
        save_config(config)
        console.print("[bold yellow]✓[/bold yellow] Paste compaction disabled.")
        console.print("[dim]Pasted text will be shown inline.[/dim]")
    else:
        console.print(f"[red]Invalid option:[/red] {setting}")
        console.print("[dim]Usage: /paste-compact [on|off][/dim]")
