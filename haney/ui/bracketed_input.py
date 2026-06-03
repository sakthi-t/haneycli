"""Bracketed paste mode input handler.

Enables terminal bracketed paste mode before reading input,
detects paste start/end escape sequences, and buffers pasted
content silently to prevent terminal flooding.

Typed characters are echoed normally. Pasted content is captured
atomically without display, and a summary notification is shown
after the paste completes.

Works on Unix (Linux/macOS) via termios. On Windows, falls back
to regular input() since bracketed paste is not supported by the
standard console host.
"""

from __future__ import annotations

import sys
import os
import select

try:
    import termios
    import tty
    _HAS_TERMIOS = True
except ImportError:
    _HAS_TERMIOS = False


# Escape sequence for paste start/end in bracketed paste mode
PASTE_START = "\x1b[200~"
PASTE_END = "\x1b[201~"

# How long to wait (seconds) before assuming paste has ended
# when the paste end marker hasn't been received yet.
PASTE_TIMEOUT = 2.0


class _BracketedInput:
    """Character-by-character input reader with bracketed paste support.

    Handles:
    - Normal typing with echo
    - Backspace (delete last char)
    - Enter to submit
    - Ctrl+C (KeyboardInterrupt)
    - Ctrl+D (EOFError)
    - Bracketed paste — silent buffering, summary on completion
    - Arrow keys (ignored for input, but don't corrupt buffer)
    """

    def __init__(self) -> None:
        self._buffer: list[str] = []
        self._paste_buffer: list[str] = []
        self._in_paste = False
        self._paste_seq_buf = ""  # For matching multi-char escape sequences
        self._had_paste = False
        self._paste_lines = 0
        self._paste_chars = 0

    def _matches_start(self, collected: str) -> int | None:
        """Check if the collected chars match the start of PASTE_START.

        Returns:
            Number of chars matching so far, or None if mismatch.
        """
        if PASTE_START.startswith(collected):
            return len(collected)
        return None

    def _matches_end(self, collected: str) -> int | None:
        """Check if the collected chars match the start of PASTE_END."""
        if PASTE_END.startswith(collected):
            return len(collected)
        return None

    def _is_escape_sequence(self, collected: str) -> bool:
        """Check if the collected chars look like an escape sequence.

        ANSI escape sequences start with \\x1b[ followed by parameters
        and a final character (letter). These include arrow keys,
        home/end, page up/down, etc.
        """
        if not collected.startswith("\x1b["):
            return False
        if len(collected) < 3:
            return True  # Still collecting
        # Check if the last char is a final byte (letter or ~)
        last = collected[-1]
        if last.isalpha() or last == "~":
            return True  # Complete escape sequence
        if len(collected) > 10:
            return True  # Too long, bail out
        return True  # Still collecting

    def _flush_escape_buf(self) -> None:
        """Flush the escape sequence buffer as regular characters."""
        if self._paste_seq_buf:
            if self._in_paste:
                self._paste_buffer.append(self._paste_seq_buf)
            else:
                self._buffer.append(self._paste_seq_buf)
                sys.stdout.write(self._paste_seq_buf)
                sys.stdout.flush()
            self._paste_seq_buf = ""

    def read_line(self, prompt: str = "") -> str:
        """Read a line of input with bracketed paste support.

        Args:
            prompt: The prompt string to display before reading.

        Returns:
            The user's input (with pasted content preserved).

        Raises:
            KeyboardInterrupt: If Ctrl+C is pressed.
            EOFError: If Ctrl+D is pressed on an empty line.
        """
        if not _HAS_TERMIOS:
            # Windows fallback — no bracketed paste support
            sys.stdout.write(prompt)
            sys.stdout.flush()
            return input()

        # Save terminal settings
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        # Reset state
        self._buffer = []
        self._paste_buffer = []
        self._in_paste = False
        self._paste_seq_buf = ""
        self._had_paste = False

        try:
            # Switch to raw mode (no echo, no line buffering)
            tty.setraw(fd)

            # Enable bracketed paste mode
            sys.stdout.write("\x1b[?2004h")
            sys.stdout.write(prompt)
            sys.stdout.flush()

            while True:
                ch = self._read_char(fd)

                if ch is None:
                    # Timeout or no data
                    if self._in_paste:
                        # Paste timed out — flush what we have
                        self._in_paste = False
                        self._flush_escape_buf()
                        self._end_paste()
                    continue

                # Handle the character; returns True when input is complete
                if self._process_char(ch):
                    break

        finally:
            # Disable bracketed paste mode
            sys.stdout.write("\x1b[?2004l")
            sys.stdout.flush()
            # Restore terminal settings
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

        return "".join(self._buffer)

    def _read_char(self, fd: int) -> str | None:
        """Read a single character from stdin with a short timeout.

        Returns the character or None on timeout.
        """
        if self._in_paste:
            timeout = PASTE_TIMEOUT
        else:
            timeout = 0.1

        rlist, _, _ = select.select([fd], [], [], timeout)
        if not rlist:
            return None

        try:
            data = os.read(fd, 1)
            if not data:
                raise EOFError("End of input")
            return data.decode("utf-8", errors="replace")
        except BlockingIOError:
            return None

    def _process_char(self, ch: str) -> bool:
        """Process a single character from stdin.

        Returns:
            True when the input line is complete (Enter pressed)
            and the read loop should break.
        """
        # ── Ctrl+C ──────────────────────────────────────
        if ch == "\x03":
            sys.stdout.write("^C\r\n")
            sys.stdout.flush()
            raise KeyboardInterrupt()

        # ── Enter (submit) ──────────────────────────────
        if ch in ("\r", "\n"):
            self._flush_escape_buf()
            if self._in_paste:
                # Enter during paste — include it in paste
                # (but usually paste won't have standalone Enter
                #  without being part of the bracketed paste)
                self._paste_buffer.append("\n")
                return False
            else:
                self._end_paste()
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                return True  # Signal the read loop to break

        # ── Backspace ───────────────────────────────────
        if ch in ("\x7f", "\x08"):
            self._flush_escape_buf()
            if self._in_paste:
                if self._paste_buffer:
                    self._paste_buffer.pop()
            elif self._buffer:
                self._buffer.pop()
                # Erase last char on screen
                sys.stdout.write("\b \b")
                sys.stdout.flush()
            return False

        # ── Ctrl+D (EOF) ────────────────────────────────
        if ch == "\x04":
            self._flush_escape_buf()
            if not self._buffer and not self._in_paste:
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                raise EOFError()
            # If there's content, ignore Ctrl+D
            return False

        # ── ESC — potential escape sequence ─────────────
        if ch == "\x1b":
            self._flush_escape_buf()
            self._paste_seq_buf = "\x1b"
            return False

        # ── Collecting escape sequence ──────────────────
        if self._paste_seq_buf:
            self._paste_seq_buf += ch

            # Check for bracketed paste start
            if self._paste_seq_buf == PASTE_START:
                self._paste_seq_buf = ""
                self._in_paste = True
                return False

            # Check for bracketed paste end
            if self._paste_seq_buf == PASTE_END:
                self._paste_seq_buf = ""
                self._in_paste = False
                self._end_paste()
                return False

            # Check if it matches a partial start/end
            match_start = self._matches_start(self._paste_seq_buf)
            match_end = self._matches_end(self._paste_seq_buf)

            if match_start is not None or match_end is not None:
                # Still could be a paste marker, keep collecting
                return False

            if self._is_escape_sequence(self._paste_seq_buf):
                # Still collecting escape sequence (arrow key, etc.)
                return False

            # Not a recognized escape sequence — flush as regular chars
            self._flush_escape_buf()
            return False

        # ── Regular character ───────────────────────────
        if self._in_paste:
            # During paste — silently buffer
            self._paste_buffer.append(ch)
        else:
            # Normal typing — echo and buffer
            self._buffer.append(ch)
            sys.stdout.write(ch)
            sys.stdout.flush()

        return False

    def _end_paste(self) -> None:
        """Handle completion of a paste operation."""
        if self._paste_buffer:
            pasted = "".join(self._paste_buffer)
            self._buffer.append(pasted)
            self._had_paste = True

            # Show compact notification
            lines = pasted.count("\n") + 1
            chars = len(pasted)
            if chars >= 1024:
                size = f"{chars / 1024:.1f} KB"
            else:
                size = f"{chars} B"

            sys.stdout.write(f" 📋 Pasted ({lines} lines, {size})")
            sys.stdout.flush()

        self._paste_buffer = []
        self._paste_seq_buf = ""


# ── Singleton ─────────────────────────────────────────────────────────────────
_bracketed_input: _BracketedInput | None = None


def get_bracketed_input() -> _BracketedInput:
    """Get or create the bracketed input reader."""
    global _bracketed_input
    if _bracketed_input is None:
        _bracketed_input = _BracketedInput()
    return _bracketed_input


def bracketed_prompt(prompt: str = "") -> str:
    """Read a line of input with bracketed paste mode enabled.

    Pasted text is captured silently and a summary is shown
    after the paste completes. This prevents terminal flooding
    when pasting large blocks of text.

    Args:
        prompt: The prompt string to display.

    Returns:
        The user's input string (with pasted content intact).

    Raises:
        KeyboardInterrupt: If Ctrl+C is pressed.
        EOFError: If Ctrl+D is pressed on empty input.
    """
    return get_bracketed_input().read_line(prompt)
