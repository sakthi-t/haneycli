"""Safe shell command execution for Haney.

Uses a blacklist approach: ALL commands are allowed by default,
EXCEPT those matching dangerous patterns (sudo, reboot, rm, etc.).

Git, Python, npm, npx, Java, and all other developer tools are
explicitly permitted. Only destructive/privileged operations are blocked.
"""

from __future__ import annotations

import re
import shlex
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


# ── Known-safe read-only commands (no confirmation needed in AUTO) ──────────

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
    "type",
    "cat",
    "head",
    "tail",
    "wc",
    "file",
    "stat",
    "du",
    "df",
    "tree",
    "echo",
    "git",
    "man",
    "help",
    "info",
    "whatis",
    "apropos",
    "true",
    "false",
    "yes",
    "test",
}

# ── Dangerous commands (blacklist) ────────────────────────────────────────────
# Only these patterns are blocked. EVERYTHING else is allowed.

DANGEROUS_PATTERNS: list[str] = [
    # File deletion / destruction
    r"\brm\b",
    r"\brmdir\b",
    r"\bdel\b",
    r"\brd\b",
    r"\bdestroy\b",
    r"\bformat\b",

    # Privilege escalation
    r"\bsudo\b",
    r"\bsu\b",
    r"\bdoas\b",

    # System power / restart
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bhalt\b",
    r"\bpoweroff\b",
    r"\binit\s+[0-6]\b",

    # Filesystem / disk
    r"\bmkfs\b",
    r"\bfdisk\b",
    r"\bdd\b",
    r"\bmount\b",
    r"\bumount\b",

    # Firewall / network
    r"\biptables\b",
    r"\bnftables\b",

    # Systemd / init
    r"\bsystemctl\b",
    r"\bservice\b",

    # Device writes (block devices only — /dev/null is safe)
    r">\s*/dev/sd",
    r">\s*/dev/nvme",
    r">\s*/dev/mmcblk",
    r">\s*/dev/hd",
    r">\s*/dev/xvd",
    r">\s*/dev/vd",
    r">\s*/dev/loop",
    r">\s*/dev/mapper",
    r">\s*/dev/dm-",
    r">\s*/dev/md",
    r"\bdd\b.*of=/dev/",

    # User / permission
    r"\bpasswd\b",
    r"\bchown\b",
    r"\bchgrp\b",
    r"chmod\s+777",

    # Pipe-to-shell (remote code execution)
    r"\bwget\b.*\|.*sh\b",
    r"\bcurl\b.*\|.*sh\b",
    r"\bwget\b.*\|.*bash\b",
    r"\bcurl\b.*\|.*bash\b",

    # Eval / exec injection
    r"\beval\b",
    r"\bexec\b",

    # Process killing
    r"\bkill\b",
    r"\bkillall\b",
    r"\bpkill\b",
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


def _extract_base_command(command: str) -> str:
    """Extract the base command from a full command string.

    Handles:
      - Simple commands: 'git status' → 'git'
      - Path-qualified: '/usr/bin/git' → 'git'
      - Piped commands checks each segment
      - Handles chained commands (&&, ;, ||)

    Args:
        command: The full command string.

    Returns:
        The base command name (first segment).
    """
    stripped = command.strip()
    if not stripped:
        return ""
    # Take first segment before any operator
    first_segment = stripped.split()[0] if stripped else ""
    # Strip path (e.g. /usr/bin/git → git)
    return Path(first_segment).name if first_segment else ""


def is_readonly_command(command: str) -> bool:
    """Check if a command is known to be read-only.

    Args:
        command: The full command string.

    Returns:
        True if the base command is read-only.
    """
    base = _extract_base_command(command)
    return base.lower() in READONLY_COMMANDS


def run_shell(
    command: str, cwd: Path | None = None, timeout: int = 60
) -> ShellResult:
    """Execute a shell command safely.

    Blocks dangerous commands (blacklist). Allows everything else.
    Runs in a subprocess with a timeout.

    Args:
        command: The command string to execute.
        cwd: Working directory for the command.
        timeout: Maximum execution time in seconds (default: 60s).

    Returns:
        ShellResult with stdout, stderr, and status.
    """
    stripped = command.strip()
    if not stripped:
        return ShellResult(
            success=False, command=command, stdout="", stderr="",
            blocked=True, message="Empty command.",
        )

    # ── Check for dangerous patterns (blacklist) ──────────
    if is_dangerous_command(stripped):
        return ShellResult(
            success=False, command=command, stdout="", stderr="",
            blocked=True,
            message=f"Blocked: '{stripped}' matches a dangerous pattern.",
        )

    # ── Everything else is allowed ────────────────────────
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
