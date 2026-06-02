"""Haney MCP — Model Context Protocol integration.

Provides a stdio-based MCP client that connects to MCP servers
(like the GitHub MCP server) and exposes their tools to Haney's
LLM tool system.
"""

from haney.mcp.server_manager import MCPServerManager
from haney.mcp.github_oauth import GitHubOAuth

__all__ = [
    "MCPServerManager",
    "GitHubOAuth",
]
