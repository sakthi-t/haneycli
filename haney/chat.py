"""Interactive chat loop for Haney.

Provides the main read-eval loop that accepts user input,
routes slash-commands, and sends chat messages to the LLM
via LiteLLM.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from haney.commands import (
    dispatch,
    set_context_manager,
    set_session_manager,
    set_perm_manager,
    set_mcp_manager,
)
from haney.llm import ChatSession
from haney.project_context import ProjectContextManager
from haney.file_context import FileContextManager
from haney.providers import is_logged_in, is_web_search_enabled
from haney.session_manager import SessionManager
from haney.config_bootstrap import bootstrap_config
from haney.permission_manager import PermissionManager
from haney.mcp.server_manager import MCPServerManager
from haney.ui.composer import Composer
from haney.paste_buffer import get_paste_buffer


def start_chat(console: Console) -> None:
    """Start the interactive chat loop.

    Creates session, project context, and enters the read-eval loop.
    Uses the Composer for a styled sticky-input experience.

    Args:
        console: Rich Console instance for output.
    """
    cwd = Path.cwd()

    # Bootstrap config — auto-populate missing keys
    bootstrap_config(cwd, console)

    # Permission manager — shared across tool system and commands
    perm_mgr = PermissionManager(cwd)
    set_perm_manager(perm_mgr)

    # Session tracking
    session_mgr = SessionManager(cwd)
    set_session_manager(session_mgr)

    # Project awareness
    ctx = ProjectContextManager()
    set_context_manager(ctx)

    # MCP server manager — shared across session and commands
    mcp_mgr = MCPServerManager(cwd=cwd, console=console)
    set_mcp_manager(mcp_mgr)

    # Shared file context — for status bar + LLM context injection
    file_ctx = FileContextManager(cwd)

    # Composer for styled input
    composer = Composer(console, session_mgr, cwd)
    composer.set_file_context(file_ctx)

    console.print()
    console.print(
        f"[dim]Session: {session_mgr.session_id}  "
        "Type /help for commands. Type /exit to quit.[/dim]"
    )
    console.print()

    chat = ChatSession(
        console,
        project_ctx=ctx,
        session_mgr=session_mgr,
        perm_mgr=perm_mgr,
        mcp_mgr=mcp_mgr,
        file_ctx=file_ctx,
    )

    try:
        while True:
            try:
                user_input = composer.ask()
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Goodbye! Haney is napping now. :3[/dim]")
                break

            if not user_input.strip():
                continue

            # Expand [pasteN] references before sending to LLM
            buf = get_paste_buffer()
            if buf.count() > 0:
                user_input = buf.expand(user_input)

            dispatch(user_input, console, chat)
            console.print()
    finally:
        # Shut down MCP servers
        mcp_mgr.shutdown_all()
        # Save session on exit
        saved = session_mgr.save()
        if saved:
            console.print(f"[dim]Session saved: {saved.name}[/dim]")
