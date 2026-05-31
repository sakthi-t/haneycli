"""Terminal composer for Haney.

Renders a visually separated input area with status info and
a styled prompt bar. Supports configurable bottom padding.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.text import Text

from haney.providers import load_config
from haney.providers import (
    get_active_provider,
    get_active_model,
    is_logged_in,
    is_web_search_enabled,
)
from haney.thinking_manager import get_thinking_mode
from haney.mode_manager import get_mode
from haney.permission_manager import get_permission_mode
from haney.session_manager import SessionManager


def _ui_config(cwd: Path | None = None) -> dict:
    cfg = load_config(cwd)
    return cfg.get("ui", {})


def _sticky_enabled(cwd: Path | None = None) -> bool:
    return _ui_config(cwd).get("sticky_input", True)


def _bottom_padding(cwd: Path | None = None) -> int:
    return _ui_config(cwd).get("input_bottom_padding", 2)


def _show_status(cwd: Path | None = None) -> bool:
    return _ui_config(cwd).get("show_status_bar", True)


class Composer:
    """Handles prompt rendering with a sticky-style composer area.

    Renders a status bar and styled prompt, with visual
    separation from conversation output.
    """

    def __init__(
        self,
        console: Console,
        session_mgr: SessionManager | None = None,
        cwd: Path | None = None,
    ) -> None:
        self.console = console
        self.session_mgr = session_mgr
        self.cwd = cwd or Path.cwd()

    def _build_status_line(self) -> str:
        """Build a single-line status string."""
        provider = get_active_provider(self.cwd) or "—"
        model = get_active_model(self.cwd) or "—"
        think = get_thinking_mode(self.cwd)
        mode = get_mode(self.cwd)
        perm = get_permission_mode(self.cwd)
        search_on = is_web_search_enabled(self.cwd)
        search_icon = "on" if search_on else "off"
        cost = f"${self.session_mgr.cost:.3f}" if self.session_mgr else "$0.000"
        ctx = ""
        try:
            from haney.project_context import ProjectContextManager
            pcm = ProjectContextManager()
            tokens = pcm.total_tokens
            if tokens > 1000:
                ctx = f"  Ctx: {tokens // 1000}k"
            elif tokens:
                ctx = f"  Ctx: {tokens}"
        except Exception:
            pass

        return (
            f"Model: {model}  Think: {think}  Mode: {mode}  "
            f"Perm: {perm}  Search: {search_icon}  Cost: {cost}{ctx}"
        )

    def _build_prompt_text(self) -> str:
        """Build the Rich-formatted prompt string."""
        provider = get_active_provider(self.cwd)
        logged_in = is_logged_in(cwd=self.cwd)
        mode = get_mode(self.cwd)
        perm = get_permission_mode(self.cwd)

        if not provider or not logged_in:
            return "[bold yellow]Haney[/bold yellow] [dim]>[/dim]"

        perm_icon = {"ask": "❓", "save": "💾", "auto": "⚡"}.get(perm, "")
        mode_color = "green" if mode == "edit" else "cyan"

        return (
            f"[dim][{perm_icon} {perm} | [/dim]"
            f"[bold {mode_color}]{mode}[/bold {mode_color}]"
            f"[dim]][/dim] "
            f"[bold yellow]Haney[/bold yellow] [dim]>[/dim]"
        )

    def render(self) -> None:
        """Render the composer area before showing the prompt.

        Prints bottom padding, a status rule, and the prompt bar.
        """
        if not _sticky_enabled(self.cwd):
            return

        # Bottom padding
        padding = _bottom_padding(self.cwd)
        for _ in range(max(0, padding)):
            self.console.print()

        # Status bar
        if _show_status(self.cwd):
            status = self._build_status_line()
            rule = Rule(
                Text(status, style="dim"),
                style="dim",
                characters="─",
            )
            self.console.print(rule)

    def ask(self) -> str:
        """Display the composer and prompt for user input.

        Returns:
            User input string.
        """
        self.render()
        return Prompt.ask(self._build_prompt_text())
