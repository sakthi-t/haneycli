"""Paste buffer for compact paste display.

Detects large/multi-line pastes and stores them in a buffer,
returning short reference labels like [paste1] instead of
flooding the terminal with pasted text.

References are auto-expanded before messages reach the LLM.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.console import Console


# ── Default thresholds ────────────────────────────────────────────────────────
DEFAULT_CHAR_THRESHOLD = 300   # Compact single-line pastes longer than this
DEFAULT_LINE_THRESHOLD = 3     # Compact pastes with more lines than this


class PasteBuffer:
    """Stores pasted text and provides compact reference labels.

    Thread-safe for single-session use. Each paste gets a unique
    short ID like 'paste1', 'paste2', etc.
    """

    def __init__(self) -> None:
        self._pastes: dict[str, str] = {}
        self._counter = 0

    def store(self, text: str) -> str:
        """Store a pasted text and return its reference label.

        Args:
            text: The full pasted text.

        Returns:
            Reference label like '[paste1]'.
        """
        self._counter += 1
        label = f"paste{self._counter}"
        self._pastes[label] = text
        return f"[{label}]"

    def get(self, label: str) -> str | None:
        """Retrieve the full text for a paste label.

        Args:
            label: The paste label (e.g., 'paste1').

        Returns:
            Full text or None if not found.
        """
        return self._pastes.get(label)

    def get_all(self) -> dict[str, str]:
        """Return all stored pastes."""
        return dict(self._pastes)

    def remove(self, label: str) -> bool:
        """Remove a paste by label.

        Returns True if the paste existed and was removed.
        """
        if label in self._pastes:
            del self._pastes[label]
            return True
        return False

    def clear(self) -> None:
        """Remove all stored pastes."""
        self._pastes.clear()

    def count(self) -> int:
        """Return the number of stored pastes."""
        return len(self._pastes)

    def expand(self, text: str) -> str:
        """Expand all [pasteN] references in text to full content.

        Args:
            text: Text that may contain [pasteN] references.

        Returns:
            Text with references replaced by full paste content.
        """
        import re

        def _replace(match: re.Match) -> str:
            label = match.group(1)
            content = self._pastes.get(label)
            if content is not None:
                return content
            return match.group(0)  # Keep unknown references as-is

        return re.sub(r"\[(paste\d+)\]", _replace, text)


# ── Singleton ─────────────────────────────────────────────────────────────────
_paste_buffer: PasteBuffer | None = None


def get_paste_buffer() -> PasteBuffer:
    """Get or create the global paste buffer."""
    global _paste_buffer
    if _paste_buffer is None:
        _paste_buffer = PasteBuffer()
    return _paste_buffer


def set_paste_buffer(buf: PasteBuffer) -> None:
    """Replace the global paste buffer (used for testing)."""
    global _paste_buffer
    _paste_buffer = buf


def should_compact(text: str, char_threshold: int = DEFAULT_CHAR_THRESHOLD,
                   line_threshold: int = DEFAULT_LINE_THRESHOLD) -> bool:
    """Determine if text should be compacted.

    Args:
        text: The input text.
        char_threshold: Max characters before compacting single-line text.
        line_threshold: Max lines before compacting multi-line text.

    Returns:
        True if the text should be compacted into a paste.
    """
    if not text:
        return False

    lines = text.split("\n")
    if len(lines) > line_threshold:
        return True
    if len(text) > char_threshold:
        return True
    return False


def format_paste_notification(label: str, text: str) -> str:
    """Format a compact notification for a stored paste.

    Args:
        label: The paste label (e.g., '[paste1]').
        text: The full pasted text.

    Returns:
        A compact notification string.
    """
    lines = text.split("\n")
    chars = len(text)
    kb = chars / 1024

    if len(lines) > 1:
        detail = f"{len(lines)} lines, {kb:.1f} KB"
    else:
        detail = f"{kb:.1f} KB"

    return f"📋 {label} — {detail}"
