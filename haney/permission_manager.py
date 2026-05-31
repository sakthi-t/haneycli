"""Permission manager for Haney.

Supports three modes: ASK (default), SAVE (session memory), AUTO.
SAVE approvals are session-only and never persist across restarts.
Even AUTO mode respects dangerous-command blocks and path safety.
"""

from __future__ import annotations

from pathlib import Path

from haney.providers import load_config, save_config

VALID_MODES = {"ask", "save", "auto"}
DEFAULT_MODE = "ask"

# Tools that are never auto-approved even in AUTO mode
ALWAYS_CONFIRM = set()


def get_permission_mode(cwd: Path | None = None) -> str:
    """Return the current permission mode from config.

    Args:
        cwd: Working directory.

    Returns:
        'ask', 'save', or 'auto'. Defaults to 'ask'.
    """
    config = load_config(cwd)
    mode = config.get("permission_mode", DEFAULT_MODE)
    return mode if mode in VALID_MODES else DEFAULT_MODE


def set_permission_mode(mode: str, cwd: Path | None = None) -> None:
    """Set the permission mode in config.json.

    Args:
        mode: 'ask', 'save', or 'auto'.
        cwd: Working directory.

    Raises:
        ValueError: If mode is invalid.
    """
    mode = mode.lower().strip()
    if mode not in VALID_MODES:
        raise ValueError(f"Invalid permission mode: '{mode}'. Use ask, save, or auto.")
    config = load_config(cwd)
    config["permission_mode"] = mode
    save_config(config, cwd)


class PermissionManager:
    """Manages the approval flow for tool execution.

    ASK mode: Always prompt.
    SAVE mode: Prompt once per tool type, remember for session.
    AUTO mode: Auto-approve all non-dangerous tools.
    """

    def __init__(self, cwd: Path | None = None) -> None:
        self.cwd = cwd
        self._session_approvals: set[str] = set()

    @property
    def mode(self) -> str:
        return get_permission_mode(self.cwd)

    @mode.setter
    def mode(self, value: str) -> None:
        set_permission_mode(value, self.cwd)
        if value != "save":
            self._session_approvals.clear()

    def set_mode(self, value: str) -> None:
        self.mode = value

    def needs_approval(self, tool_name: str) -> bool:
        """Check if a tool needs user confirmation.

        Args:
            tool_name: Name of the tool being called.

        Returns:
            True if confirmation is required.
        """
        mode = self.mode

        if mode == "auto":
            return False
        if mode == "save" and tool_name in self._session_approvals:
            return False
        return True

    def approve_session(self, tool_name: str) -> None:
        """Mark a tool type as approved for the current session.

        Args:
            tool_name: Tool name to remember.
        """
        self._session_approvals.add(tool_name)

    @property
    def session_approvals(self) -> set[str]:
        return self._session_approvals.copy()
