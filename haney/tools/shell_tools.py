"""Safe shell command execution for Haney.

Allows a whitelist of safe commands, blocks dangerous ones,
and requires confirmation before execution.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ShellResult:
    """Result of a shell command execution."""

    success: bool
    command: str
    stdout: str
    stderr: str
    blocked: bool = False
    message: str = ""


# ── Safe commands (whitelist) ─────────────────────────────────────────────────

SAFE_COMMANDS: set[str] = {
    "pwd",
    "ls",
    "dir",
    "cat",
    "head",
    "tail",
    "wc",
    "find",
    "grep",
    "echo",
    "date",
    "whoami",
    "hostname",
    "uname",
    "env",
    "printenv",
    "which",
    "whereis",
    "git",
}

# Commands that are always safe regardless of args
READONLY_COMMANDS: set[str] = {
    "pwd",
    "ls",
    "dir",
    "date",
    "whoami",
    "hostname",
    "uname",
    "env",
    "printenv",
    "which",
    "whereis",
}

# ── Dangerous commands (blacklist) ────────────────────────────────────────────

DANGEROUS_PATTERNS: list[str] = [
    r"\brm\b",
    r"\bsudo\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bmkfs\b",
    r"\bformat\b",
    r"\bdel\b",
    r"\brd\b",
    r"\brmdir\b",
    r"chmod\s+777",
    r"\bdestroy\b",
    r"\bkill\b",
    r"\bfdisk\b",
    r"\bdd\b",
    r"\bmount\b",
    r"\bumount\b",
    r"\biptables\b",
    r"\bsystemctl\b",
    r">\s*/dev/",
    r"\bpasswd\b",
    r"\bchown\b",
    r"\bchgrp\b",
    r"\bwget\b.*\|.*sh\b",
    r"\bcurl\b.*\|.*sh\b",
    r"\beval\b",
    r"\bexec\b",
]

_DANGEROUS_RE = re.compile("|".join(DANGEROUS_PATTERNS), re.IGNORECASE)


def is_dangerous_command(command: str) -> bool:
    """Check if a shell command is dangerous.

    Args:
        command: The full command string.

    Returns:
        True if the command matches a dangerous pattern.
    """
    return bool(_DANGEROUS_RE.search(command))


def _is_allowed(command: str) -> bool:
    """Check if a command is in the allowed set.

    Args:
        command: The full command string.

    Returns:
        True if allowed.
    """
    base = command.strip().split()[0] if command.strip() else ""
    # Allow git subcommands
    if base == "git":
        return True
    return base in SAFE_COMMANDS


def run_shell(
    command: str, cwd: Path | None = None, timeout: int = 30
) -> ShellResult:
    """Execute a shell command safely.

    Blocks dangerous commands. Runs safe ones in a subprocess
    with a timeout.

    Args:
        command: The command string to execute.
        cwd: Working directory for the command.
        timeout: Maximum execution time in seconds.

    Returns:
        ShellResult with stdout, stderr, and status.
    """
    stripped = command.strip()
    if not stripped:
        return ShellResult(
            success=False, command=command, stdout="", stderr="",
            blocked=True, message="Empty command.",
        )

    if is_dangerous_command(stripped):
        return ShellResult(
            success=False, command=command, stdout="", stderr="",
            blocked=True,
            message=f"Blocked: '{stripped}' may be destructive.",
        )

    if not _is_allowed(stripped):
        return ShellResult(
            success=False, command=command, stdout="", stderr="",
            blocked=True,
            message=f"Blocked: '{stripped}' is not in the allowed command set.",
        )

    try:
        result = subprocess.run(
            stripped,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
        )
    except subprocess.TimeoutExpired:
        return ShellResult(
            success=False, command=command, stdout="", stderr="",
            message=f"Command timed out after {timeout}s.",
        )
    except OSError as exc:
        return ShellResult(
            success=False, command=command, stdout="", stderr="",
            message=f"Command failed: {exc}",
        )

    return ShellResult(
        success=result.returncode == 0,
        command=command,
        stdout=result.stdout,
        stderr=result.stderr,
        message=(
            f"Completed (exit {result.returncode})"
            if result.returncode == 0
            else f"Failed (exit {result.returncode})"
        ),
    )
