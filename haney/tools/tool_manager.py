"""Tool Manager for Haney.

Registers available tools, handles the approval flow,
executes tool calls from the LLM, and manages the tool-call loop.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from haney.tools.file_tools import (
    FileToolResult,
    read_file,
    write_file,
    edit_file,
    rename_file,
    delete_file,
    list_directory,
    restore_file,
    list_trash,
)
from haney.tools.shell_tools import ShellResult, run_shell, is_dangerous_command
from haney.mode_manager import guard_tool, get_mode
from haney.providers import load_config
from haney.permission_manager import PermissionManager

# MCP tools have the prefix "mcp__"
MCP_TOOL_PREFIX = "mcp__"

# ── Tool definitions for LiteLLM ──────────────────────────────────────────────

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file. No confirmation required.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file to read.",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file. Requires user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path for the new file.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace text in a file using exact match. Requires user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file to edit.",
                    },
                    "old_text": {
                        "type": "string",
                        "description": "Exact text to find and replace.",
                    },
                    "new_text": {
                        "type": "string",
                        "description": "Replacement text.",
                    },
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rename_file",
            "description": "Rename or move a file. Requires user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "old_path": {
                        "type": "string",
                        "description": "Current relative path.",
                    },
                    "new_path": {
                        "type": "string",
                        "description": "New relative path.",
                    },
                },
                "required": ["old_path", "new_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Move a file to trash (safe delete). Requires user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file to delete.",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and directories. No confirmation required.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path (default: '.').",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell_command",
            "description": "Run a safe shell command. Requires user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute.",
                    }
                },
                "required": ["command"],
            },
        },
    },
]

# ── Safety levels ─────────────────────────────────────────────────────────────

READ_ONLY_TOOLS = {"read_file", "list_directory"}
WRITE_TOOLS = {"write_file", "edit_file", "rename_file", "delete_file", "run_shell_command"}


def _needs_approval(tool_name: str) -> bool:
    """Check if a tool requires user approval.

    Args:
        tool_name: Name of the tool.

    Returns:
        True if approval is required.
    """
    return tool_name in WRITE_TOOLS


# ── Tool Manager ──────────────────────────────────────────────────────────────

class ToolManager:
    """Manages tool execution with safety checks and approval flow.

    Integrates with LiteLLM tool calling — provides tool definitions,
    executes requested tools, and formats results for the LLM.
    Supports MCP (Model Context Protocol) tools via MCPServerManager.
    """

    def __init__(
        self, console: Console, cwd: Path | None = None, mcp_manager=None
    ) -> None:
        """Initialise the tool manager.

        Args:
            console: Rich Console for approval prompts.
            cwd: Project root directory. Defaults to current.
            mcp_manager: Optional MCPServerManager for MCP tools.
        """
        self.console = console
        self.cwd = (cwd or Path.cwd()).resolve()
        self.permissions = PermissionManager(self.cwd)
        self.mcp_manager = mcp_manager

    @property
    def tool_definitions(self) -> list[dict[str, Any]]:
        """Return tool schemas, filtered by current mode.

        In PLAN mode, only read-only tools are exposed to the LLM.
        In EDIT mode, all tools are available (including MCP tools).
        """
        mode = get_mode(self.cwd)

        if mode == "plan":
            base = [t for t in TOOL_DEFINITIONS if t["function"]["name"] in READ_ONLY_TOOLS]
        else:
            base = list(TOOL_DEFINITIONS)

        # Add MCP tools (treated as write tools, only in EDIT mode)
        if mode == "edit" and self.mcp_manager is not None:
            try:
                mcp_tools = self.mcp_manager.get_all_tool_definitions()
                base.extend(mcp_tools)
            except Exception:
                pass  # MCP tools are optional; don't break on errors

        return base

    def execute_tool_call(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> str:
        """Validate, get approval, execute a tool, and return a result string.

        Args:
            tool_name: Name of the tool to execute.
            arguments: Tool arguments from the LLM.

        Returns:
            A human-readable result string for the LLM.
        """
        # ── Route MCP tools ──────────────────────────────────
        if tool_name.startswith(MCP_TOOL_PREFIX):
            return self._execute_mcp_tool(tool_name, arguments)

        # ── Find handler ──────────────────────────────────────
        handler = _TOOL_HANDLERS.get(tool_name)
        if handler is None:
            return f"Error: Unknown tool '{tool_name}'."

        # ── Mode guard (PLAN vs EDIT) ──────────────────────
        block_msg = guard_tool(tool_name, self.cwd)
        if block_msg:
            self.console.print(f"[yellow]⛔ {block_msg}[/yellow]")
            return block_msg

        # ── Permission-based approval ──────────────────────
        if _needs_approval(tool_name) and self.permissions.needs_approval(tool_name):
            if not self._request_approval(tool_name, arguments):
                return f"Tool '{tool_name}' was declined by the user."
            # SAVE mode: remember this approval for the session
            if self.permissions.mode == "save":
                self.permissions.approve_session(tool_name)

        # ── Execute ───────────────────────────────────────────
        try:
            result = handler(self.cwd, **arguments)
        except TypeError as exc:
            return f"Error: Invalid arguments for {tool_name}: {exc}"
        except Exception as exc:
            return f"Error executing {tool_name}: {exc}"

        return self._format_result(tool_name, result)

    def _execute_mcp_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> str:
        """Execute an MCP tool through the MCP server manager.

        Args:
            tool_name: Namespaced MCP tool name (e.g. 'mcp__github__create_issue').
            arguments: Tool arguments.

        Returns:
            Result string.
        """
        if self.mcp_manager is None:
            return f"Error: MCP is not configured. No MCP manager available."

        # MCP tools are write tools — check mode
        block_msg = guard_tool("run_shell_command", self.cwd)
        if block_msg:
            return block_msg

        # Permission check
        if self.permissions.needs_approval("run_shell_command"):
            if not self._request_approval(tool_name, arguments):
                return f"MCP tool '{tool_name}' was declined by the user."
            if self.permissions.mode == "save":
                self.permissions.approve_session("run_shell_command")

        try:
            return self.mcp_manager.execute_tool(tool_name, arguments)
        except Exception as exc:
            return f"Error executing MCP tool '{tool_name}': {exc}"

    def _request_approval(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> bool:
        """Ask the user for confirmation via Rich prompt.

        Args:
            tool_name: Tool being requested.
            arguments: Tool arguments for display.

        Returns:
            True if approved.
        """
        desc = self._describe_action(tool_name, arguments)
        panel = Panel(
            desc,
            title=f"Tool Request — {tool_name}",
            border_style="yellow",
            title_align="left",
        )
        self.console.print(panel)
        return Confirm.ask("Proceed?", default=True)

    def _describe_action(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> str:
        """Build a human-readable description of what the tool will do.

        Args:
            tool_name: Tool name.
            arguments: Tool arguments.

        Returns:
            Description string.
        """
        if tool_name == "write_file":
            path = arguments.get("path", "?")
            content = arguments.get("content", "")
            lines = content.count("\n") + 1
            return f"Create: [bold]{path}[/bold]\n\nSize: {len(content)} chars, {lines} lines"
        elif tool_name == "edit_file":
            path = arguments.get("path", "?")
            old = arguments.get("old_text", "")
            new = arguments.get("new_text", "")
            return (
                f"Modify: [bold]{path}[/bold]\n\n"
                f"Find:\n  [red]{old[:200]}[/red]\n\n"
                f"Replace with:\n  [green]{new[:200]}[/green]"
            )
        elif tool_name == "rename_file":
            old = arguments.get("old_path", "?")
            new = arguments.get("new_path", "?")
            return f"Rename:\n  [red]{old}[/red]\n  →\n  [green]{new}[/green]"
        elif tool_name == "delete_file":
            path = arguments.get("path", "?")
            return f"Delete:\n  [red]{path}[/red]\n\nDestination:\n  .haney/trash/"
        elif tool_name == "run_shell_command":
            cmd = arguments.get("command", "?")
            return f"Command:\n  [bold cyan]{cmd}[/bold cyan]"
        return str(arguments)

    def _format_result(self, tool_name: str, result: Any) -> str:
        """Format a tool execution result for the LLM.

        Args:
            tool_name: Tool name.
            result: The tool's return value.

        Returns:
            Formatted string.
        """
        if isinstance(result, FileToolResult):
            if not result.success:
                return f"Error: {result.message}"
            out = result.message
            if result.content_preview:
                out += f"\n\n{result.content_preview}"
            return out

        if isinstance(result, ShellResult):
            if result.blocked:
                return f"Blocked: {result.message}"
            out = result.message
            if result.stdout:
                out += f"\n\n{result.stdout.strip()}"
            if result.stderr:
                out += f"\n\n[stderr]\n{result.stderr.strip()}"
            return out

        return str(result)


# ── Tool handler registry ─────────────────────────────────────────────────────

_TOOL_HANDLERS: dict[str, Callable[..., Any]] = {
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "rename_file": rename_file,
    "delete_file": delete_file,
    "list_directory": list_directory,
    "run_shell_command": lambda root, command: run_shell(command, cwd=root),
}
