"""GitHub OAuth device flow for MCP authentication.

Implements the GitHub device flow (RFC 8628) to obtain
a personal access token for the GitHub MCP server.
"""

from __future__ import annotations

import time
import webbrowser
from dataclasses import dataclass
from typing import Any

from rich.console import Console

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

# ── GitHub OAuth endpoints ─────────────────────────────────────────────────────

GITHUB_DEVICE_CODE_URL = "https://github.com/login/device/code"
GITHUB_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_VERIFICATION_URI = "https://github.com/login/device"

# Default Haney OAuth app client ID (can be overridden)
DEFAULT_CLIENT_ID = "Iv23li1nOANQ7o4iFjPS"  # Placeholder — register a real one

# Scopes needed for GitHub MCP
DEFAULT_SCOPES = "repo,read:user,read:org"


@dataclass
class DeviceCodeResponse:
    """Response from the device/code endpoint."""

    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


@dataclass
class AccessTokenResponse:
    """Response from the access_token endpoint."""

    access_token: str
    token_type: str
    scope: str | None = None


class GitHubOAuthError(Exception):
    """Raised when GitHub OAuth fails."""


class GitHubOAuth:
    """Handles GitHub device flow OAuth.

    Usage:
        oauth = GitHubOAuth(console)
        token = oauth.login()
        # token is stored; use it as GITHUB_PERSONAL_ACCESS_TOKEN
    """

    def __init__(
        self,
        console: Console,
        client_id: str | None = None,
        scopes: str | None = None,
    ) -> None:
        """Initialise the OAuth handler.

        Args:
            console: Rich Console for user interaction.
            client_id: GitHub OAuth app client ID.
            scopes: Space-separated OAuth scopes.
        """
        if not HAS_HTTPX:
            raise GitHubOAuthError(
                "httpx is required for GitHub OAuth. "
                "Install it with: pip install httpx"
            )

        self.console = console
        self.client_id = client_id or DEFAULT_CLIENT_ID
        self.scopes = scopes or DEFAULT_SCOPES

    def login(self) -> str:
        """Perform the full device flow login.

        Returns:
            GitHub personal access token.

        Raises:
            GitHubOAuthError: If login fails at any step.
        """
        # Step 1: Request device code
        self.console.print()
        self.console.print("[bold]Starting GitHub OAuth device flow…[/bold]")
        self.console.print()

        device_response = self._request_device_code()

        # Step 2: Prompt user to authenticate
        self.console.print(
            f"  [bold cyan]1.[/bold cyan] Visit: "
            f"[underline]{device_response.verification_uri}[/underline]"
        )
        self.console.print(
            f"  [bold cyan]2.[/bold cyan] Enter code: "
            f"[bold yellow]{device_response.user_code}[/bold yellow]"
        )
        self.console.print()

        # Try to open the browser
        try:
            if webbrowser.open(device_response.verification_uri):
                self.console.print("[dim]Opening browser…[/dim]")
            else:
                self.console.print(
                    "[dim]Could not open browser. "
                    "Please visit the URL above manually.[/dim]"
                )
        except Exception:
            self.console.print(
                "[dim]Could not open browser. "
                "Please visit the URL above manually.[/dim]"
            )

        self.console.print()
        self.console.print("[dim]Waiting for authorization…[/dim]")

        # Step 3: Poll for access token
        token = self._poll_for_token(
            device_response.device_code,
            device_response.interval,
            device_response.expires_in,
        )

        return token

    def _request_device_code(self) -> DeviceCodeResponse:
        """Request a device code from GitHub.

        Returns:
            DeviceCodeResponse with codes.

        Raises:
            GitHubOAuthError: On failure.
        """
        try:
            with httpx.Client() as client:
                response = client.post(
                    GITHUB_DEVICE_CODE_URL,
                    data={
                        "client_id": self.client_id,
                        "scope": self.scopes,
                    },
                    headers={
                        "Accept": "application/json",
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise GitHubOAuthError(
                f"Failed to request device code: {exc}"
            ) from exc
        except Exception as exc:
            raise GitHubOAuthError(
                f"Unexpected error requesting device code: {exc}"
            ) from exc

        if "error" in data:
            raise GitHubOAuthError(
                f"GitHub returned error: {data.get('error_description', data['error'])}"
            )

        return DeviceCodeResponse(
            device_code=data["device_code"],
            user_code=data["user_code"],
            verification_uri=data.get(
                "verification_uri", GITHUB_VERIFICATION_URI
            ),
            expires_in=data.get("expires_in", 900),
            interval=data.get("interval", 5),
        )

    def _poll_for_token(
        self,
        device_code: str,
        interval: int,
        expires_in: int,
    ) -> str:
        """Poll GitHub for an access token until granted or expired.

        Args:
            device_code: The device code from step 1.
            interval: Polling interval in seconds.
            expires_in: Maximum polling time in seconds.

        Returns:
            Access token string.

        Raises:
            GitHubOAuthError: On timeout or failure.
        """
        deadline = time.monotonic() + expires_in

        with httpx.Client() as client:
            while time.monotonic() < deadline:
                time.sleep(interval)

                try:
                    response = client.post(
                        GITHUB_ACCESS_TOKEN_URL,
                        data={
                            "client_id": self.client_id,
                            "device_code": device_code,
                            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                        },
                        headers={
                            "Accept": "application/json",
                        },
                        timeout=30.0,
                    )
                    response.raise_for_status()
                    data = response.json()
                except httpx.HTTPError as exc:
                    self.console.print(
                        f"[yellow]Polling error: {exc}. Retrying…[/yellow]"
                    )
                    continue

                if "error" in data:
                    error_code = data["error"]

                    if error_code == "authorization_pending":
                        # User hasn't authorised yet — keep polling
                        continue
                    elif error_code == "slow_down":
                        # Server asked us to slow down
                        interval += 5
                        continue
                    elif error_code == "expired_token":
                        raise GitHubOAuthError(
                            "Device code expired. Please try again."
                        )
                    else:
                        raise GitHubOAuthError(
                            f"GitHub returned error: "
                            f"{data.get('error_description', error_code)}"
                        )

                # Success!
                if "access_token" in data:
                    return data["access_token"]

        raise GitHubOAuthError(
            "Device flow timed out. Please try again."
        )

    @staticmethod
    def check_token(token: str) -> dict[str, Any]:
        """Verify a GitHub token and return user info.

        Args:
            token: GitHub personal access token.

        Returns:
            User info dict with 'login' key.

        Raises:
            GitHubOAuthError: If the token is invalid.
        """
        if not HAS_HTTPX:
            raise GitHubOAuthError("httpx is required.")

        try:
            with httpx.Client() as client:
                response = client.get(
                    "https://api.github.com/user",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github+json",
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise GitHubOAuthError(
                f"Invalid token or network error: {exc}"
            ) from exc
