"""Exa web search integration for Haney.

Provides SearchManager that wraps the Exa API for automatic
web search, with results merged into LLM context.

Credentials are stored in .haney/config.json under:
  {"search": {"exa_api_key": "..."}}

Falls back to the EXA_API_KEY environment variable.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from exa_py import Exa
from rich.console import Console

from haney.providers import load_config, save_config


def get_exa_api_key(cwd: Path | None = None) -> str | None:
    """Retrieve the Exa API key.

    Checks config.json first, then the EXA_API_KEY environment variable.

    Args:
        cwd: Working directory. Defaults to current directory.

    Returns:
        API key string, or None if not configured.
    """
    # 1. Config file
    config = load_config(cwd)
    search_cfg = config.get("search", {})
    stored = search_cfg.get("exa_api_key")
    if stored:
        return stored

    # 2. Environment variable
    return os.environ.get("EXA_API_KEY")


def is_search_logged_in(cwd: Path | None = None) -> bool:
    """Check if an Exa API key is configured.

    Args:
        cwd: Working directory.

    Returns:
        True if an Exa key is available.
    """
    return get_exa_api_key(cwd) is not None


def login_search(api_key: str, cwd: Path | None = None) -> None:
    """Store the Exa API key in config.json.

    Args:
        api_key: The Exa API key.
        cwd: Working directory.
    """
    config = load_config(cwd)
    if "search" not in config:
        config["search"] = {}
    config["search"]["exa_api_key"] = api_key
    save_config(config, cwd)


def logout_search(cwd: Path | None = None) -> None:
    """Remove the Exa API key from config.json.

    Args:
        cwd: Working directory.
    """
    config = load_config(cwd)
    search_cfg = config.get("search", {})
    search_cfg.pop("exa_api_key", None)
    if search_cfg:
        config["search"] = search_cfg
    else:
        config.pop("search", None)
    save_config(config, cwd)


class SearchManager:
    """Manages Exa web search operations.

    Reads the Exa API key from .haney/config.json (set via /login exa)
    or the EXA_API_KEY environment variable as fallback.
    """

    def __init__(self, console: Console, cwd: Path | None = None) -> None:
        """Initialise the search manager.

        Args:
            console: Rich Console for status output.
            cwd: Working directory. Defaults to current.
        """
        self.console = console
        self.cwd = cwd or Path.cwd()
        self._client: Exa | None = None

    @property
    def enabled(self) -> bool:
        """Check if web search is enabled in config."""
        config = load_config(self.cwd)
        return config.get("web_search", True)

    @property
    def _exa(self) -> Exa | None:
        """Return the Exa client, initialising on first access."""
        if self._client is None:
            key = get_exa_api_key(self.cwd)
            if key:
                self._client = Exa(api_key=key)
        return self._client

    @property
    def available(self) -> bool:
        """Check if Exa is configured and search is enabled."""
        return self._exa is not None and self.enabled

    def search(self, query: str, num_results: int = 5) -> str | None:
        """Execute an Exa search and return formatted context.

        Args:
            query: The search query string.
            num_results: Number of results to fetch (default 5).

        Returns:
            Formatted markdown string of search results, or None on failure.
        """
        if not self.available:
            return None

        self.console.print("🔍 [bold cyan]Searching Exa…[/bold cyan]")

        try:
            results = self._exa.search_and_contents(
                query,
                type="auto",
                num_results=num_results,
                text=True,
                highlights=True,
            )
        except Exception:
            return None

        if not results or not results.results:
            return None

        lines = ["## Web Search Results\n"]
        for i, r in enumerate(results.results, 1):
            title = r.title or "Untitled"
            url = r.url or ""
            snippet = ""
            if r.highlights:
                snippet = " ".join(r.highlights)[:500]
            elif r.text:
                snippet = r.text[:500]

            lines.append(f"{i}. **[{title}]({url})**")
            if snippet:
                lines.append(f"   {snippet}")
            lines.append("")

        return "\n".join(lines)
