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

    # Extra environment variables to pass to the MCP server process
    extra_env: dict[str, str] = field(default_factory=dict)

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
    "duckduckgo": MCPServerConfig(
        display_name="DuckDuckGo",
        command="uvx",
        args=["duckduckgo-mcp-server"],
        env_token_key="",
        description=(
            "Web search and content fetching via DuckDuckGo — "
            "no API key required, rate-limited and LLM-friendly output"
        ),
        requires_auth=False,
        requires_node=False,
        npm_package="",
    ),
    "mdn": MCPServerConfig(
        display_name="MDN Web Docs",
        command="npx",
        args=["-y", "mdn-mcp"],
        env_token_key="",
        extra_env={
            # Opt out of Mozilla first-party analytics.
            # The mdn-mcp server reads this env var and sends the
            # X-Moz-1st-Party-Data-Opt-Out: 1 header with outbound
            # requests to MDN APIs. Set to "0" to allow analytics.
            "MOZ_OPT_OUT": "1",
        },
        description=(
            "⚠️  Experimental — MDN queries are logged (see privacy notice). "
            "MDN Web Docs reference — search documentation, fetch pages, "
            "check browser compatibility, CSS definitions, and HTTP reference. "
            "Opt-out of analytics via MOZ_OPT_OUT=1 env var."
        ),
        requires_auth=False,
        requires_node=True,
        npm_package="mdn-mcp",
    ),
    "filesystem": MCPServerConfig(
        display_name="Filesystem",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "."],
        env_token_key="",
        description=(
            "Secure filesystem access — read, write, edit, move, search files "
            "and browse directory trees within allowed paths. "
            "Scoped to configured directories only."
        ),
        requires_auth=False,
        requires_node=True,
        npm_package="@modelcontextprotocol/server-filesystem",
    ),
    "sequential-thinking": MCPServerConfig(
        display_name="Sequential Thinking",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-sequential-thinking"],
        env_token_key="",
        description=(
            "Structured step-by-step reasoning — break down complex problems "
            "into sequential thoughts with revision, branching, and hypothesis "
            "tracking. Pure local reasoning, no API calls."
        ),
        requires_auth=False,
        requires_node=True,
        npm_package="@modelcontextprotocol/server-sequential-thinking",
    ),
    "langchain": MCPServerConfig(
        display_name="LangChain",
        command="npx",
        args=["-y", "langchain-mcp"],
        env_token_key="",
        description=(
            "LangChain, LangGraph & DeepAgents knowledge base — "
            "search documentation, debug LangGraph agents locally "
            "with Polly-like trace analysis"
        ),
        requires_auth=False,
        requires_node=True,
        npm_package="langchain-mcp",
    ),
    "playwright": MCPServerConfig(
        display_name="Playwright",
        command="npx",
        args=["-y", "@playwright/mcp"],
        env_token_key="",
        description=(
            "Browser automation — navigate web pages, take screenshots, "
            "click elements, fill forms, and extract content. Uses Playwright "
            "to control Chromium, Firefox, or WebKit browsers. "
            "Run `npx playwright install` once to install browser binaries."
        ),
        requires_auth=False,
        requires_node=True,
        npm_package="@playwright/mcp",
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
