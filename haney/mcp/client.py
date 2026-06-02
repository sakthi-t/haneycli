"""MCP JSON-RPC 2.0 client.

Implements the MCP protocol handshake and core methods
over a stdio transport.
"""

from __future__ import annotations

import logging
from typing import Any

from haney.mcp.transport import MCPTransport, MCPTransportError

logger = logging.getLogger(__name__)

# ── Protocol constants ────────────────────────────────────────────────────────

MCP_VERSION = "2024-11-05"
JSONRPC_VERSION = "2.0"


class MCPClientError(Exception):
    """Raised when the MCP client encounters a protocol-level error."""


class MCPClient:
    """JSON-RPC 2.0 client for an MCP server process.

    Handles the MCP initialisation handshake and exposes
    core methods: list_tools, call_tool, and ping.
    """

    def __init__(self, transport: MCPTransport) -> None:
        """Initialise the client with a transport.

        Args:
            transport: An MCPTransport instance with a running server.
        """
        self.transport = transport
        self._request_id = 0
        self._initialized = False

    # ── Lifecycle ────────────────────────────────────────────────────

    def initialize(self, client_name: str = "haney", client_version: str = "1.0.0") -> dict:
        """Perform the MCP initialisation handshake.

        Sends the initialize request and the initialized notification.

        Args:
            client_name: Name of this MCP client.
            client_version: Version of this MCP client.

        Returns:
            The server's capabilities response.

        Raises:
            MCPClientError: If the handshake fails.
        """
        if self._initialized:
            return self._capabilities

        # Step 1: Send initialize request
        response = self._call(
            "initialize",
            {
                "protocolVersion": MCP_VERSION,
                "clientInfo": {
                    "name": client_name,
                    "version": client_version,
                },
                "capabilities": {
                    "tools": {},
                },
            },
        )

        if "error" in response:
            err = response["error"]
            raise MCPClientError(
                f"MCP initialize failed: {err.get('message', str(err))}"
            )

        self._capabilities = response.get("result", {})
        server_info = self._capabilities.get("serverInfo", {})
        logger.info(
            "MCP server initialised: %s v%s",
            server_info.get("name", "unknown"),
            server_info.get("version", "unknown"),
        )

        # Step 2: Send initialized notification
        try:
            self._send_notification("notifications/initialized", {})
        except MCPTransportError:
            # Some servers don't handle this; non-fatal
            logger.debug("Initialized notification failed (non-fatal)")

        self._initialized = True
        return self._capabilities

    # ── Public API ────────────────────────────────────────────────────

    def list_tools(self) -> list[dict]:
        """Fetch the list of available tools from the MCP server.

        Returns:
            List of tool definition dicts.

        Raises:
            MCPClientError: If the request fails.
        """
        response = self._call("tools/list", {})
        if "error" in response:
            err = response["error"]
            raise MCPClientError(
                f"tools/list failed: {err.get('message', str(err))}"
            )
        return response.get("result", {}).get("tools", [])

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict:
        """Call a tool on the MCP server.

        Args:
            tool_name: Name of the tool to call.
            arguments: Tool arguments.

        Returns:
            The tool result from the server.

        Raises:
            MCPClientError: If the call fails.
        """
        response = self._call(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments,
            },
        )

        if "error" in response:
            err = response["error"]
            raise MCPClientError(
                f"tools/call '{tool_name}' failed: {err.get('message', str(err))}"
            )

        result = response.get("result", {})
        # MCP tools return content as a list of content items
        content_items = result.get("content", [])
        is_error = result.get("isError", False)

        return {
            "content": content_items,
            "is_error": is_error,
        }

    def ping(self) -> bool:
        """Ping the MCP server.

        Returns:
            True if the server responds successfully.
        """
        try:
            response = self._call("ping", {})
            return "error" not in response
        except (MCPTransportError, MCPClientError):
            return False

    # ── Internal JSON-RPC helpers ────────────────────────────────────

    def _call(self, method: str, params: dict) -> dict:
        """Send a JSON-RPC request and return the response.

        Args:
            method: The MCP method name.
            params: Parameters for the method.

        Returns:
            The JSON-RPC response dict.
        """
        self._request_id += 1
        request = {
            "jsonrpc": JSONRPC_VERSION,
            "id": self._request_id,
            "method": method,
            "params": params,
        }

        self.transport.send(request)
        response = self.transport.receive()

        if response is None:
            raise MCPClientError(
                f"No response for method '{method}' (id={self._request_id})"
            )

        if response.get("id") != self._request_id:
            logger.warning(
                "MCP response id mismatch: expected %d, got %s",
                self._request_id,
                response.get("id"),
            )

        return response

    def _send_notification(self, method: str, params: dict) -> None:
        """Send a JSON-RPC notification (no response expected).

        Args:
            method: The MCP method name.
            params: Parameters for the method.
        """
        notification = {
            "jsonrpc": JSONRPC_VERSION,
            "method": method,
            "params": params,
        }
        self.transport.send(notification)
