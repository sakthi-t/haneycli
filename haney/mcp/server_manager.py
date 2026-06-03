"""MCP server manager — multi-server registry and lifecycle.

Manages all connected MCP servers: spawn, handshake, tool discovery,
health checks, and graceful shutdown. Integrates with Haney's config.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console

from haney.mcp.transport import MCPTransport, MCPTransportError
from haney.mcp.client import MCPClient, MCPClientError
from haney.mcp.tool_adapter import (
    mcp_tool_to_haney_def,
    parse_tool_name,
    format_tool_result,
    MCP_TOOL_PREFIX,
)
from haney.mcp.server_configs import get_server_config

logger = logging.getLogger(__name__)


@dataclass
class ConnectedServer:
    """Represents one connected MCP server."""

    name: str
    config: dict
    transport: MCPTransport | None = None
    client: MCPClient | None = None
    tools: list[dict] = field(default_factory=list)
    tool_defs: list[dict] = field(default_factory=list)
    enabled: bool = True


class MCPServerManager:
    """Manages the lifecycle of multiple MCP servers.

    Integrates with Haney's config system and provides
    tool definitions to the ToolManager.
    """

    def __init__(
        self,
        cwd: Path | None = None,
        console: Console | None = None,
    ) -> None:
        """Initialise the MCP server manager.

        Args:
            cwd: Working directory.
            console: Rich Console for logging.
        """
        self.cwd = cwd or Path.cwd()
        self.console = console
        self._servers: dict[str, ConnectedServer] = {}

    # ── Server lifecycle ──────────────────────────────────────────────

    def connect(
        self,
        server_name: str,
        config: dict | None = None,
    ) -> ConnectedServer:
        """Connect to an MCP server — spawn, handshake, discover tools.

        Args:
            server_name: Server name (e.g. 'github').
            config: Optional server config override.

        Returns:
            ConnectedServer with tools populated.

        Raises:
            MCPTransportError: If the server can't be started.
            MCPClientError: If the handshake fails.
        """
        if server_name in self._servers:
            return self._servers[server_name]

        # Get predefined config
        srv_config = get_server_config(server_name)
        if srv_config is None and config is None:
            raise ValueError(f"Unknown MCP server: {server_name}")

        # Build run config
        run_cfg = config or {}
        command = run_cfg.get("command", srv_config.command if srv_config else "")
        args = run_cfg.get("args", srv_config.args if srv_config else [])

        if not command:
            raise ValueError(
                f"No command configured for MCP server '{server_name}'."
            )

        # Build environment
        env: dict[str, str] = dict(run_cfg.get("env", {}))

        # Merge extra_env from predefined server config (takes lower priority)
        if srv_config and srv_config.extra_env:
            for key, value in srv_config.extra_env.items():
                if key not in env:
                    env[key] = value

        token = run_cfg.get("token")
        token_key = (
            srv_config.env_token_key
            if srv_config
            else run_cfg.get("env_token_key", "")
        )
        if token and token_key:
            env[token_key] = token

        if self.console:
            self.console.print(
                f"[dim]Starting {server_name} MCP server: "
                f"{command} {' '.join(args)}[/dim]"
            )

        # Spawn transport
        transport = MCPTransport(
            command=command,
            args=args,
            env=env,
            cwd=self.cwd,
        )

        try:
            transport.start()
        except MCPTransportError as exc:
            if self.console:
                self.console.print(
                    f"[red]Failed to start {server_name} MCP server: {exc}[/red]"
                )
            raise

        # Handshake
        client = MCPClient(transport)
        try:
            capabilities = client.initialize(
                client_name="haney",
                client_version="1.0.0",
            )
        except MCPClientError as exc:
            transport.stop()
            if self.console:
                self.console.print(
                    f"[red]MCP handshake failed for {server_name}: {exc}[/red]"
                )
            raise

        # Discover tools
        try:
            mcp_tools = client.list_tools()
        except MCPClientError as exc:
            transport.stop()
            if self.console:
                self.console.print(
                    f"[red]Failed to list tools for {server_name}: {exc}[/red]"
                )
            raise

        # Convert to Haney tool definitions
        tool_defs = [
            mcp_tool_to_haney_def(tool, server_name)
            for tool in mcp_tools
        ]

        server = ConnectedServer(
            name=server_name,
            config=run_cfg,
            transport=transport,
            client=client,
            tools=mcp_tools,
            tool_defs=tool_defs,
        )

        self._servers[server_name] = server

        if self.console:
            self.console.print(
                f"[bold green]✓[/bold green] {server_name} MCP connected "
                f"— {len(tool_defs)} tool(s) available"
            )
            for td in tool_defs:
                self.console.print(
                    f"  [dim cyan]{td['function']['name']}[/dim cyan]"
                )

        return server

    def disconnect(self, server_name: str) -> bool:
        """Disconnect from an MCP server.

        Args:
            server_name: Server name.

        Returns:
            True if disconnected, False if not connected.
        """
        if server_name not in self._servers:
            return False

        server = self._servers.pop(server_name)

        if server.transport:
            server.transport.stop()

        if self.console:
            self.console.print(
                f"[dim]Disconnected from {server_name} MCP server.[/dim]"
            )

        return True

    def shutdown_all(self) -> None:
        """Stop all connected MCP servers."""
        names = list(self._servers.keys())
        for name in names:
            self.disconnect(name)

    # ── Tool integration ──────────────────────────────────────────────

    def get_all_tool_definitions(self) -> list[dict[str, Any]]:
        """Get merged tool definitions from all connected MCP servers.

        Returns:
            List of LiteLLM-compatible tool definition dicts.
        """
        all_tools: list[dict] = []
        for server in self._servers.values():
            if server.enabled:
                all_tools.extend(server.tool_defs)
        return all_tools

    def execute_tool(
        self,
        namespaced_name: str,
        arguments: dict[str, Any],
    ) -> str:
        """Execute an MCP tool by its namespaced name.

        Args:
            namespaced_name: Like 'mcp__github__create_issue'.
            arguments: Tool arguments.

        Returns:
            Formatted result string for the LLM.
        """
        parsed = parse_tool_name(namespaced_name)
        if parsed is None:
            return f"Error: Not a valid MCP tool name: {namespaced_name}"

        server_name, tool_name = parsed

        if server_name not in self._servers:
            return f"Error: MCP server '{server_name}' is not connected."

        server = self._servers[server_name]
        if server.client is None:
            return f"Error: MCP server '{server_name}' has no active client."

        try:
            result = server.client.call_tool(tool_name, arguments)
        except MCPClientError as exc:
            return f"Error executing MCP tool '{tool_name}': {exc}"
        except MCPTransportError as exc:
            return f"Error: MCP server '{server_name}' transport error: {exc}"

        return format_tool_result(tool_name, result)

    # ── Status ────────────────────────────────────────────────────────

    def is_connected(self, server_name: str) -> bool:
        """Check if a server is connected.

        Args:
            server_name: Server name.

        Returns:
            True if connected and alive.
        """
        if server_name not in self._servers:
            return False
        server = self._servers[server_name]
        return (
            server.transport is not None
            and server.transport.is_alive()
        )

    def get_connected_servers(self) -> list[str]:
        """Get list of connected server names.

        Returns:
            List of connected server names.
        """
        return [
            name
            for name, server in self._servers.items()
            if server.transport and server.transport.is_alive()
        ]

    def get_tool_count(self) -> int:
        """Get total number of MCP tools across all servers.

        Returns:
            Tool count.
        """
        return sum(
            len(s.tool_defs)
            for s in self._servers.values()
            if s.enabled
        )
