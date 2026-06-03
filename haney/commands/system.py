"""System commands: /help, /version, /clear, /exit."""

from __future__ import annotations

import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from haney.config import HANEY_DIR, VERSION


def cmd_help(console: Console, args: list[str]) -> None:
    """Display available commands.

    Args:
        console: Rich Console instance for output.
        args: Additional arguments (unused).
    """
    commands: list[tuple[str, str]] = [
        # Phase 1
        ("/help", "Display this help message"),
        ("/version", "Show Haney version and project info"),
        ("/clear", "Clear the terminal screen"),
        ("/exit", "Exit Haney gracefully"),
        # Phase 2 — Provider Management
        ("/login <provider>", "Connect an LLM provider or Exa search"),
        ("/logout [provider]", "Disconnect from a provider"),
        ("/models [provider]", "List all available models"),
        ("/model [name]", "Show or set the active model"),
        ("/provider", "Show current provider status"),
        # Phase 5 — Project Awareness
        ("/project", "Show project status and loaded files"),
        ("/reload", "Re-scan project files"),
        ("/context", "Show loaded context details"),
        ("/init", "Generate starter project-awareness files"),
        # Phase 7 — Safe Tools
        ("/trash", "Show files in trash"),
        ("/restore <file>", "Restore file from trash"),
        # Phase 8 — Session Management
        ("/history", "Show recent sessions"),
        ("/session", "Current session info"),
        ("/stats", "Token and cost metrics"),
        # Phase 10 & 11 — Memory & Compact
        ("/remember <text>", "Append to memory.md"),
        ("/summary", "Show project summary"),
        ("/compact", "Compact conversation + update summary"),
        # Phase 12 & 13 — Thinking Modes & Status
        ("/think [off|low|medium|high]", "Show/set thinking mode"),
        ("/status", "Show full runtime status"),
        # Phase 14 — Plan / Edit Mode
        ("/plan", "Switch to PLAN mode (discussion only)"),
        ("/edit", "Switch to EDIT mode (tools enabled)"),
        ("/mode", "Show current execution mode"),
        # Permission
        ("/permission [ask|save|auto]", "Set approval mode"),
        # MCP
        ("/mcp login <server>", "Authenticate with an MCP server"),
        ("/mcp logout <server>", "Clear MCP credentials"),
        ("/mcp connect <server>", "Connect to an MCP server"),
        ("/mcp disconnect [server]", "Disconnect MCP server(s)"),
        ("/mcp status", "Show MCP connection status"),
        ("/mcp servers", "List available MCP servers"),
        # Paste buffer
        ("/pastes [clear|<id>]", "List or manage compacted paste buffers"),
        ("/paste-compact [on|off]", "Toggle compact paste display"),
    ]

    table = Table(title="Available Commands", border_style="blue", title_justify="left")
    table.add_column("Command", style="bold cyan", no_wrap=True)
    table.add_column("Description", style="dim")

    for name, desc in commands:
        table.add_row(name, desc)

    console.print(table)
    console.print(
        "\n[dim]Supported providers: openai, anthropic, deepseek, gemini, openrouter, groq, exa[/dim]"
    )
    console.print(
        "[dim]Attach files with @filename in chat messages. Use /attachments to view.[/dim]"
    )
    console.print(
        "[dim]Large pastes are auto-compacted to [pasteN] labels. Use /pastes to list. "
        "Use /paste-compact off to disable.[/dim]"
    )


def cmd_version(console: Console, args: list[str]) -> None:
    """Display the current Haney version.

    Args:
        console: Rich Console instance for output.
        args: Additional arguments (unused).
    """
    version_text = f"Haney v{VERSION}"
    panel = Panel(version_text, border_style="yellow", title="Version", title_align="left")
    console.print(panel)


def cmd_clear(console: Console, args: list[str]) -> None:
    """Clear the terminal screen.

    Also clears file attachments if a session is active.
    Note: session.clear() is called from dispatch(),
    this handler only clears the screen.

    Args:
        console: Rich Console instance for output.
        args: Additional arguments (unused).
    """
    console.clear()


def cmd_exit(console: Console, args: list[str]) -> None:
    """Exit Haney gracefully.

    Args:
        console: Rich Console instance for output.
        args: Additional arguments (unused).
    """
    console.print("\n[dim]Goodbye! Haney is napping now. :3[/dim]")
    sys.exit(0)
