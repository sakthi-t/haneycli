"""Command handlers package.

Splits the former monolithic commands.py (~2540 lines) into a
package of focused modules:

    _base.py         — Command dataclass
    _state.py        — Shared module-level state and set_* functions
    system.py        — /help, /version, /clear, /exit
    provider.py      — /login, /logout, /models, /model, /provider
    project_cmds.py  — /project, /reload, /context, /init
    tool_cmds.py     — /trash, /restore
    session_cmds.py  — /history, /session, /stats
    memory_cmds.py   — /remember, /summary, /compact
    mode_cmds.py     — /think, /status, /plan, /edit, /mode, /permission
    mcp_cmds.py      — /mcp + all sub-commands
    paste_cmds.py    — /pastes, /paste-compact

Public API (used by chat.py):
    dispatch()
    set_context_manager()
    set_session_manager()
    set_perm_manager()
    set_mcp_manager()
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console

from haney.config import COMMAND_PREFIX
from haney.commands._base import Command
from haney.commands._state import (
    set_context_manager,
    set_session_manager,
    set_perm_manager,
    set_mcp_manager,
)


# ── Command registry ──────────────────────────────────────────────────────────

def get_commands() -> dict[str, Command]:
    """Return a mapping of command names to Command objects.

    Imports command modules lazily to keep the hot path fast.
    """
    from haney.commands.system import cmd_help, cmd_version, cmd_clear, cmd_exit
    from haney.commands.provider import cmd_login, cmd_logout, cmd_models, cmd_model, cmd_provider
    from haney.commands.project_cmds import cmd_project, cmd_reload, cmd_context, cmd_init
    from haney.commands.tool_cmds import cmd_trash, cmd_restore
    from haney.commands.session_cmds import cmd_history, cmd_session, cmd_stats
    from haney.commands.memory_cmds import cmd_remember, cmd_summary
    from haney.commands.mode_cmds import cmd_think, cmd_status, cmd_plan, cmd_edit, cmd_mode_show, cmd_permission
    from haney.commands.mcp_cmds import cmd_mcp
    from haney.commands.paste_cmds import cmd_pastes, cmd_paste_compact

    return {
        # Phase 1 — System
        "/help": Command(name="/help", description="Display help", handler=cmd_help),
        "/version": Command(name="/version", description="Show version", handler=cmd_version),
        "/clear": Command(name="/clear", description="Clear screen", handler=cmd_clear),
        "/exit": Command(name="/exit", description="Exit Haney", handler=cmd_exit),
        # Phase 2 — Provider
        "/login": Command(name="/login", description="Connect a provider", handler=cmd_login),
        "/logout": Command(name="/logout", description="Disconnect provider", handler=cmd_logout),
        "/models": Command(name="/models", description="List models", handler=cmd_models),
        "/model": Command(name="/model", description="Show/set model", handler=cmd_model),
        "/provider": Command(name="/provider", description="Show provider status", handler=cmd_provider),
        # Phase 5 — Project
        "/project": Command(name="/project", description="Project status", handler=cmd_project),
        "/reload": Command(name="/reload", description="Re-scan project", handler=cmd_reload),
        "/context": Command(name="/context", description="Context details", handler=cmd_context),
        "/init": Command(name="/init", description="Generate project files", handler=cmd_init),
        # Phase 7 — Tools
        "/trash": Command(name="/trash", description="Show trash contents", handler=cmd_trash),
        "/restore": Command(name="/restore", description="Restore file from trash", handler=cmd_restore),
        # Phase 8 — Session
        "/history": Command(name="/history", description="Show recent sessions", handler=cmd_history),
        "/session": Command(name="/session", description="Current session info", handler=cmd_session),
        "/stats": Command(name="/stats", description="Token & cost metrics", handler=cmd_stats),
        # Phase 10 & 11 — Memory
        "/remember": Command(name="/remember", description="Save to memory.md", handler=cmd_remember),
        "/summary": Command(name="/summary", description="Show project summary", handler=cmd_summary),
        "/compact": Command(name="/compact", description="Compact conversation", handler=cmd_remember),
        # Phase 12 & 13 — Thinking & Status
        "/think": Command(name="/think", description="Show/set thinking mode", handler=cmd_think),
        "/status": Command(name="/status", description="Runtime status", handler=cmd_status),
        # Phase 14 — Mode
        "/plan": Command(name="/plan", description="Switch to PLAN mode", handler=cmd_plan),
        "/edit": Command(name="/edit", description="Switch to EDIT mode", handler=cmd_edit),
        "/mode": Command(name="/mode", description="Show current mode", handler=cmd_mode_show),
        # Permission
        "/permission": Command(name="/permission", description="Show/set permission mode", handler=cmd_permission),
        # MCP
        "/mcp": Command(name="/mcp", description="Manage MCP servers", handler=cmd_mcp),
        # Paste buffer
        "/pastes": Command(name="/pastes", description="List/manage paste buffer", handler=cmd_pastes),
        "/paste-compact": Command(name="/paste-compact", description="Toggle paste compaction", handler=cmd_paste_compact),
    }


# ── Dispatch ──────────────────────────────────────────────────────────────────

def dispatch(user_input: str, console: Console, session: "ChatSession | None" = None) -> None:
    """Parse user input and dispatch to the appropriate handler.

    If the input starts with the command prefix, it is routed to the
    command handler. Otherwise, it is treated as a chat message and
    sent to the LLM via the ChatSession.

    Args:
        user_input: The raw user input string.
        console: Rich Console instance for output.
        session: Active ChatSession for LLM calls. Created if not provided.
    """
    if TYPE_CHECKING:
        from haney.llm import ChatSession

    stripped = user_input.strip()

    if not stripped.startswith(COMMAND_PREFIX):
        if session is None:
            from haney.llm import ChatSession
            session = ChatSession(console)

        try:
            session.send(stripped)
        except RuntimeError as exc:
            console.print(f"[red]Error:[/red] {exc}")
        except Exception as exc:
            console.print(f"[red]Unexpected error:[/red] {exc}")
        return

    commands = get_commands()
    parts = stripped.split(maxsplit=1)
    cmd_name = parts[0].lower()
    cmd_args = parts[1].split() if len(parts) > 1 else []

    # /clear also clears conversation and attachments
    if cmd_name == "/clear" and session is not None:
        session.clear()

    # /attachments shows file context via session
    if cmd_name == "/attachments":
        if session is not None:
            session.file_ctx.display_summary(console)
        else:
            console.print("[dim]No active session. Attach files with @filename in a chat message.[/dim]")
        return

    # /compact needs the session for LLM call and message truncation
    if cmd_name == "/compact":
        if session is not None:
            from haney.commands.memory_cmds import cmd_compact
            cmd_compact(console, session)
        else:
            console.print("[yellow]No active session. Start a conversation first.[/yellow]")
        return

    if cmd_name in commands:
        commands[cmd_name].handler(console, cmd_args)
    else:
        console.print(f"[red]Unknown command:[/red] {cmd_name}")
        console.print("[dim]Type /help to see available commands.[/dim]")


# Re-export for backward compatibility
__all__ = [
    "Command",
    "dispatch",
    "get_commands",
    "set_context_manager",
    "set_session_manager",
    "set_perm_manager",
    "set_mcp_manager",
]
