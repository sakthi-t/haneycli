"""Execution mode manager for Haney.

Supports PLAN (discussion-only, default) and EDIT (tool-enabled)
modes. Mode persists in .haney/config.json across sessions.
"""

from __future__ import annotations

from pathlib import Path

from haney.providers import load_config, save_config

VALID_MODES = {"plan", "edit"}
DEFAULT_MODE = "plan"
WRITE_TOOLS = {"write_file", "edit_file", "rename_file", "delete_file", "run_shell_command"}


def get_mode(cwd: Path | None = None) -> str:
    """Return the current execution mode.

    Args:
        cwd: Working directory.

    Returns:
        'plan' or 'edit'. Defaults to 'plan'.
    """
    config = load_config(cwd)
    mode = config.get("mode", DEFAULT_MODE)
    return mode if mode in VALID_MODES else DEFAULT_MODE


def set_mode(mode: str, cwd: Path | None = None) -> None:
    """Set the execution mode in config.json.

    Args:
        mode: 'plan' or 'edit'.
        cwd: Working directory.

    Raises:
        ValueError: If mode is invalid.
    """
    mode = mode.lower().strip()
    if mode not in VALID_MODES:
        raise ValueError(f"Invalid mode: '{mode}'. Use 'plan' or 'edit'.")
    config = load_config(cwd)
    config["mode"] = mode
    save_config(config, cwd)


def is_edit_mode(cwd: Path | None = None) -> bool:
    """Check if the current mode allows tool execution.

    Args:
        cwd: Working directory.

    Returns:
        True if mode is 'edit'.
    """
    return get_mode(cwd) == "edit"


def guard_tool(tool_name: str, cwd: Path | None = None) -> str | None:
    """Check if a tool is allowed in the current mode.

    Read-only tools are always allowed. Write tools are blocked
    in PLAN mode.

    Args:
        tool_name: Name of the tool being requested.
        cwd: Working directory.

    Returns:
        None if the tool is allowed, or a user-facing block message.
    """
    if tool_name not in WRITE_TOOLS:
        return None  # read-only — always allowed

    if get_mode(cwd) == "plan":
        return (
            "You are currently in PLAN mode. "
            "Switch to EDIT mode using /edit to allow project modifications."
        )

    return None  # edit mode — allowed
