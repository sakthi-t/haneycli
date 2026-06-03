"""Module-level shared state for command handlers.

This is a leaf module — it imports from the main Haney packages
but never from sibling command modules.  All command handler
modules import from here to access shared managers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from haney.project_context import ProjectContextManager
from haney.permission_manager import PermissionManager

if TYPE_CHECKING:
    from haney.session_manager import SessionManager
    from haney.mcp.server_manager import MCPServerManager

# ── Project context manager ────────────────────────────────────────────────
_ctx_manager: ProjectContextManager | None = None


def set_context_manager(ctx: ProjectContextManager) -> None:
    """Set the shared project context manager.

    Called once by chat.py when the session starts.
    """
    global _ctx_manager
    _ctx_manager = ctx


def get_context_manager() -> ProjectContextManager:
    """Return the shared context manager, creating one if needed."""
    global _ctx_manager
    if _ctx_manager is None:
        _ctx_manager = ProjectContextManager()
    return _ctx_manager


# ── Session manager ─────────────────────────────────────────────────────────
_session_mgr: "SessionManager | None" = None


def set_session_manager(mgr: "SessionManager") -> None:
    """Set the shared session manager. Called by chat.py."""
    global _session_mgr
    _session_mgr = mgr


def get_session_manager() -> "SessionManager | None":
    """Return the shared session manager."""
    return _session_mgr


# ── Permission manager ─────────────────────────────────────────────────────
_perm_mgr: PermissionManager = PermissionManager()


def set_perm_manager(mgr: PermissionManager) -> None:
    """Set the shared permission manager. Called by chat.py."""
    global _perm_mgr
    _perm_mgr = mgr


def get_perm_manager() -> PermissionManager:
    """Return the shared permission manager."""
    return _perm_mgr


# ── MCP manager ─────────────────────────────────────────────────────────────
_mcp_mgr: "MCPServerManager | None" = None


def set_mcp_manager(mgr: "MCPServerManager") -> None:
    """Set the shared MCP manager. Called by chat.py."""
    global _mcp_mgr
    _mcp_mgr = mgr


def get_mcp_manager() -> "MCPServerManager | None":
    """Return the shared MCP manager."""
    return _mcp_mgr
