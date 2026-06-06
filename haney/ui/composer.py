"""Terminal composer for Haney.

Renders a visually separated input area with status info and
a styled prompt bar. Supports configurable bottom padding and
compact paste display for large/multi-line pastes.

Uses bracketed paste mode to capture pasted text silently,
preventing terminal flooding when large blocks are pasted.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
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
from haney.paste_buffer import (
    get_paste_buffer,
    should_compact,
    format_paste_notification,
)
from haney.ui.bracketed_input import bracketed_prompt


def _rich_to_plain(text: str) -> str:
    """Strip Rich markup tags to produce plain terminal text.

    Removes style tags like [bold], [dim], [/dim], etc.
    while preserving the visible content.

    Args:
        text: Rich-formatted prompt string.

    Returns:
        Plain text suitable for raw terminal output.
    """
    import re
    # Remove Rich style tags: [style], [/style], [style attr=val], etc.
    return re.sub(r"\[/?[a-zA-Z_][a-zA-Z0-9_.#= -]*\]", "", text)


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
        self._file_ctx = None  # set later via set_file_context()

    def set_file_context(self, file_ctx) -> None:
        """Bind a FileContextManager for status bar display.

        Called after ChatSession creates the shared file context.
        """
        self._file_ctx = file_ctx

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
        if self.session_mgr and self.session_mgr.context_tokens:
            ctx_tokens = self.session_mgr.context_tokens
            if ctx_tokens >= 1000:
                ctx = f"  Ctx: {ctx_tokens / 1000:.0f}k"
            elif ctx_tokens:
                ctx = f"  Ctx: {ctx_tokens}"

        # ── Attachment indicator ────────────────────────────
        attach = ""
        if self._file_ctx is not None and not self._file_ctx.empty:
            attach = f"  {self._file_ctx.compact_status()}"

        return (
            f"Model: {model}  Think: {think}  Mode: {mode}  "
            f"Perm: {perm}  Search: {search_icon}  Cost: {cost}{ctx}{attach}"
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

        # Status bar
        if _show_status(self.cwd):
            status = self._build_status_line()
            rule = Rule(
                Text(status, style="dim"),
                style="dim",
                characters="─",
            )
            self.console.print(rule)

    def render_bottom(self) -> None:
        """Render a separator below the input area after submission.

        Prints a dim rule (bottom line) and configurable padding
        to visually separate the typing area from conversation output
        and lift the area up from the bottom of the screen.
        """
        if not _sticky_enabled(self.cwd):
            return

        if _ui_config(self.cwd).get("show_bottom_rule", True):
            rule = Rule(style="dim", characters="─")
            self.console.print(rule)

        after_padding = _ui_config(self.cwd).get("input_after_padding", 3)
        for _ in range(max(0, after_padding)):
            self.console.print()

    def ask(self) -> str:
        """Display the composer and prompt for user input.

        Uses bracketed paste mode to capture pasted text silently.
        Large/multi-line pastes are stored in the paste buffer and
        shown as compact [pasteN] labels instead of flooding the
        terminal with pasted text.

        Returns:
            User input string (may contain [pasteN] references).
        """
        self.render()

        # Build the prompt (uses Rich markup for styling).
        # Strip Rich markup tags for the raw terminal prompt since
        # bracketed_prompt renders to the raw terminal.
        prompt_raw = _rich_to_plain(self._build_prompt_text())

        try:
            raw_input = bracketed_prompt(prompt_raw)
        except (KeyboardInterrupt, EOFError):
            raise

        self.render_bottom()

        if not raw_input.strip():
            return ""

        # ── Check for paste compaction ──────────────────────────
        ui_cfg = _ui_config(self.cwd)
        if ui_cfg.get("paste_compact", True) and should_compact(
            raw_input,
            char_threshold=ui_cfg.get("paste_char_threshold", 300),
            line_threshold=ui_cfg.get("paste_line_threshold", 3),
        ):
            buf = get_paste_buffer()
            label = buf.store(raw_input)
            notification = format_paste_notification(label, raw_input)
            self.console.print(f"  {notification}")
            return label

        return raw_input
