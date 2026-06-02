"""MCP transport layer — subprocess lifecycle for MCP servers.

Spawns MCP server processes, manages JSON-line stdio communication,
and handles health checks and graceful shutdown.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class MCPTransportError(Exception):
    """Raised when MCP transport encounters an error."""


class MCPTransport:
    """Manages a single MCP server subprocess.

    Handles spawn, JSON-RPC message passing over stdin/stdout,
    health checks, and termination.
    """

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: Path | None = None,
        startup_timeout: float = 30.0,
    ) -> None:
        """Initialise the transport.

        Args:
            command: The command to run (e.g. 'npx').
            args: Arguments for the command.
            env: Extra environment variables.
            cwd: Working directory for the subprocess.
            startup_timeout: Max seconds to wait for startup.
        """
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.cwd = cwd or Path.cwd()
        self.startup_timeout = startup_timeout
        self._process: subprocess.Popen | None = None

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        """Spawn the MCP server subprocess."""
        if self._process is not None:
            raise MCPTransportError("MCP server is already running.")

        full_env = os.environ.copy()
        full_env.update(self.env)

        full_cmd = [self.command] + self.args
        logger.debug("Starting MCP server: %s", " ".join(full_cmd))

        try:
            self._process = subprocess.Popen(
                full_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=self.cwd,
                env=full_env,
            )
        except FileNotFoundError as exc:
            raise MCPTransportError(
                f"Command not found: {self.command}. "
                f"Is it installed? ({exc})"
            ) from exc
        except Exception as exc:
            raise MCPTransportError(
                f"Failed to start MCP server: {exc}"
            ) from exc

        # Wait briefly for the process to stabilise
        time.sleep(0.5)
        if not self.is_alive():
            stderr_output = self._read_stderr()
            raise MCPTransportError(
                f"MCP server exited immediately. "
                f"stderr: {stderr_output[:500]}"
            )

    def stop(self) -> None:
        """Gracefully terminate the MCP server."""
        if self._process is None:
            return

        logger.debug("Stopping MCP server…")
        try:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.debug("MCP server did not terminate; killing.")
                self._process.kill()
                self._process.wait(timeout=2)
        except Exception as exc:
            logger.warning("Error stopping MCP server: %s", exc)
        finally:
            self._process = None

    # ── Health ────────────────────────────────────────────────────────

    def is_alive(self) -> bool:
        """Check if the subprocess is still running."""
        return self._process is not None and self._process.poll() is None

    # ── I/O ───────────────────────────────────────────────────────────

    def send(self, payload: dict) -> None:
        """Send a JSON-RPC message to the server.

        Args:
            payload: JSON-serialisable dict to send.
        """
        if not self.is_alive():
            raise MCPTransportError("MCP server is not running.")

        message = json.dumps(payload, ensure_ascii=False)
        logger.debug("MCP send: %s", message[:500])

        try:
            self._process.stdin.write(message + "\n")
            self._process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise MCPTransportError(
                f"Failed to write to MCP server: {exc}"
            ) from exc

    def receive(self, timeout: float = 10.0) -> dict | None:
        """Read a single JSON-RPC message from the server.

        Args:
            timeout: Maximum seconds to wait.

        Returns:
            Parsed JSON dict, or None if the server closed stdout.
        """
        if not self.is_alive():
            raise MCPTransportError("MCP server is not running.")

        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            line = self._process.stdout.readline()
            if not line:
                # stdout closed
                stderr_output = self._read_stderr()
                raise MCPTransportError(
                    f"MCP server closed stdout. "
                    f"stderr: {stderr_output[:500]}"
                )

            line = line.strip()
            if not line:
                continue

            logger.debug("MCP recv: %s", line[:500])
            try:
                return json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning("MCP received non-JSON line: %s", line[:200])
                continue

        raise MCPTransportError(
            f"MCP server did not respond within {timeout}s."
        )

    def _read_stderr(self) -> str:
        """Non-blocking read of accumulated stderr."""
        if self._process is None or self._process.stderr is None:
            return ""
        self._process.stderr.flush()
        import select
        ready, _, _ = select.select([self._process.stderr], [], [], 0.1)
        if ready:
            return self._process.stderr.read()
        return ""
