"""Pre-defined MCP server configurations.

Defines default commands and arguments for supported MCP servers.
Users can override these via .haney/config.json.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""

    # Display name
    display_name: str

    # Command to run
    command: str

    # Arguments for the command
    args: list[str] = field(default_factory=list)

    # Environment variable name for the auth token
    env_token_key: str = ""

    # Description
    description: str = ""

    # Whether token-based auth is required
    requires_auth: bool = True

    # Whether npx/node is required
    requires_node: bool = False

    # Required npm package (if any)
    npm_package: str = ""


# ── Predefined servers ─────────────────────────────────────────────────────────

MCP_SERVERS: dict[str, MCPServerConfig] = {
    "github": MCPServerConfig(
        display_name="GitHub",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env_token_key="GITHUB_PERSONAL_ACCESS_TOKEN",
        description="GitHub repository management — issues, PRs, search, and more",
        requires_auth=True,
        requires_node=True,
        npm_package="@modelcontextprotocol/server-github",
    ),
    "stackoverflow": MCPServerConfig(
        display_name="Stack Overflow",
        command="npx",
        args=["-y", "mcp-remote", "https://mcp.stackoverflow.com"],
        env_token_key="",
        description=(
            "Stack Overflow knowledge base — search questions, "
            "retrieve answers, comments, and accepted solutions"
        ),
        requires_auth=False,  # OAuth handled by mcp-remote automatically
        requires_node=True,
        npm_package="mcp-remote",
    ),
}


def get_server_config(server_name: str) -> MCPServerConfig | None:
    """Get the predefined config for an MCP server.

    Args:
        server_name: Server name (e.g. 'github').

    Returns:
        MCPServerConfig or None if unknown.
    """
    return MCP_SERVERS.get(server_name.lower())
