"""Session management for Haney.

Tracks session lifecycle, messages, token usage, cost,
and persists sessions as JSON in .haney/sessions/.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from haney.config import HANEY_DIR
from haney.providers import get_active_provider, get_active_model

# ── Approximate pricing (per 1M tokens, USD) ──────────────────────────────────

MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o":         {"input": 2.50, "output": 10.00},
    "gpt-4o-mini":    {"input": 0.15, "output": 0.60},
    "gpt-4.1":        {"input": 2.00, "output": 8.00},
    "gpt-4.1-mini":   {"input": 0.40, "output": 1.60},
    "gpt-4.1-nano":   {"input": 0.10, "output": 0.40},
    "o3":             {"input": 10.00, "output": 40.00},
    "o3-mini":        {"input": 1.10, "output": 4.40},
    "o4-mini":        {"input": 1.10, "output": 4.40},
    "o1":             {"input": 15.00, "output": 60.00},
    "o1-mini":        {"input": 3.00, "output": 12.00},
    "gpt-4-turbo":    {"input": 10.00, "output": 30.00},
    "gpt-4":          {"input": 30.00, "output": 60.00},
    "deepseek-chat":  {"input": 0.27, "output": 1.10},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19},
    "deepseek-v4-pro": {"input": 0.27, "output": 1.10},
    "deepseek-v4": {"input": 0.27, "output": 1.10},
    "claude-opus-4-20250514":  {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-3.5-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3.5-haiku": {"input": 0.80, "output": 4.00},
    "claude-3-opus":   {"input": 15.00, "output": 75.00},
    "claude-3-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-haiku":  {"input": 0.25, "output": 1.25},
    "gemini-2.5-flash":    {"input": 0.15, "output": 0.60},
    "gemini-2.5-pro":      {"input": 1.25, "output": 10.00},
    "gemini-2.0-flash":    {"input": 0.10, "output": 0.40},
    "gemini-1.5-flash":    {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro":      {"input": 1.25, "output": 5.00},
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
    "mixtral-8x7b-32768":      {"input": 0.24, "output": 0.24},
}
DEFAULT_PRICING = {"input": 1.00, "output": 4.00}


def _get_model_pricing(model: str) -> dict[str, float]:
    """Get pricing for a model, with fuzzy prefix matching.

    Falls back to DEFAULT_PRICING if no match is found.
    Strips provider prefixes like 'openai/', 'deepseek/', etc.
    """
    # Normalize: strip ALL provider prefixes (e.g.
    # openrouter/anthropic/claude-sonnet-4 → claude-sonnet-4)
    normalized = model.lower()
    PROVIDER_PREFIXES = (
        "openai/", "deepseek/", "anthropic/", "gemini/", "groq/", "openrouter/"
    )
    while True:
        stripped = False
        for prefix in PROVIDER_PREFIXES:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
                stripped = True
                break
        if not stripped:
            break

    # Exact match
    if normalized in MODEL_PRICING:
        return MODEL_PRICING[normalized]

    # Prefix/substring match
    for key, pricing in MODEL_PRICING.items():
        if normalized.startswith(key) or key.startswith(normalized):
            return pricing

    return DEFAULT_PRICING


@dataclass
class SessionRecord:
    """A recorded session with all metrics."""

    session_id: str
    started_at: str
    provider: str
    model: str
    messages: list[dict[str, str]] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    api_calls: int = 0
    cost: float = 0.0
    ended_at: str = ""


class SessionManager:
    """Manages the current session lifecycle and persistence.

    Creates a new session on start, tracks token usage and
    cost after every LLM call, and saves to .haney/sessions/
    on exit.
    """

    def __init__(self, cwd: Path | None = None) -> None:
        """Initialise and start a new session.

        Args:
            cwd: Working directory. Defaults to current.
        """
        self.cwd = (cwd or Path.cwd()).resolve()
        now = datetime.now(timezone.utc)
        self.session_id = _generate_session_id(self.cwd, now)
        self.started_at = now

        self._input_tokens: int = 0
        self._output_tokens: int = 0
        self._api_calls: int = 0
        self._cost: float = 0.0
        self._messages: list[dict[str, str]] = []
        self._last_context_tokens: int = 0

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def started_at_iso(self) -> str:
        return self.started_at.isoformat()

    @property
    def provider(self) -> str:
        return get_active_provider(self.cwd) or "unknown"

    @property
    def model(self) -> str:
        return get_active_model(self.cwd) or "unknown"

    @property
    def started_at_display(self) -> str:
        return self.started_at.strftime("%H:%M")

    @property
    def message_count(self) -> int:
        return len(self._messages)

    @property
    def input_tokens(self) -> int:
        return self._input_tokens

    @property
    def output_tokens(self) -> int:
        return self._output_tokens

    @property
    def total_tokens(self) -> int:
        return self._input_tokens + self._output_tokens

    @property
    def api_calls(self) -> int:
        return self._api_calls

    @property
    def cost(self) -> float:
        return self._cost

    @property
    def context_tokens(self) -> int:
        """Estimated tokens in the last conversation context."""
        return self._last_context_tokens

    # ── Tracking ──────────────────────────────────────────────────────────

    def record_message(self, role: str, content: str) -> None:
        """Add a message to the session record.

        Args:
            role: 'user' or 'assistant'.
            content: Message content.
        """
        self._messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def record_usage(
        self, model: str, prompt_tokens: int, completion_tokens: int
    ) -> None:
        """Update token and cost counters after an API call.

        Args:
            model: Model name used for this call.
            prompt_tokens: Tokens consumed by the prompt.
            completion_tokens: Tokens generated.
        """
        self._api_calls += 1
        self._input_tokens += prompt_tokens
        self._output_tokens += completion_tokens
        self._last_context_tokens = prompt_tokens

        pricing = _get_model_pricing(model)
        cost_in = (prompt_tokens / 1_000_000) * pricing["input"]
        cost_out = (completion_tokens / 1_000_000) * pricing["output"]
        self._cost += cost_in + cost_out

    # ── Persistence ───────────────────────────────────────────────────────

    def save(self) -> Path | None:
        """Save the current session to .haney/sessions/<id>.json.

        Returns:
            Path to the saved file, or None on failure.
        """
        sessions_dir = self.cwd / HANEY_DIR / "sessions"
        try:
            sessions_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None

        record: dict = {
            "session_id": self.session_id,
            "started_at": self.started_at_iso,
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "provider": self.provider,
            "model": self.model,
            "messages": self._messages,
            "input_tokens": self._input_tokens,
            "output_tokens": self._output_tokens,
            "api_calls": self._api_calls,
            "cost": round(self._cost, 6),
            "last_context_tokens": self._last_context_tokens,
        }

        filepath = sessions_dir / f"{self.session_id}.json"
        try:
            filepath.write_text(json.dumps(record, indent=2), encoding="utf-8")
            return filepath
        except OSError:
            return None

    # ── History ───────────────────────────────────────────────────────────

    @staticmethod
    def list_sessions(cwd: Path | None = None) -> list[dict]:
        """List all saved sessions, newest first.

        Args:
            cwd: Working directory.

        Returns:
            List of session summary dicts.
        """
        target = (cwd or Path.cwd()) / HANEY_DIR / "sessions"
        if not target.is_dir():
            return []

        sessions: list[dict] = []
        for f in sorted(target.glob("*.json"), reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                sessions.append({
                    "session_id": data.get("session_id", f.stem),
                    "started_at": data.get("started_at", ""),
                    "provider": data.get("provider", "?"),
                    "model": data.get("model", "?"),
                    "messages": len(data.get("messages", [])),
                    "api_calls": data.get("api_calls", 0),
                    "cost": data.get("cost", 0),
                })
            except (json.JSONDecodeError, OSError):
                continue

        return sessions


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generate_session_id(cwd: Path, now: datetime) -> str:
    """Generate a unique session ID like '2026-05-31-001'.

    Args:
        cwd: Working directory.
        now: Current datetime.

    Returns:
        Session ID string.
    """
    date_prefix = now.strftime("%Y-%m-%d")
    sessions_dir = cwd / HANEY_DIR / "sessions"
    max_n = 0
    if sessions_dir.is_dir():
        for p in sessions_dir.glob(f"{date_prefix}-*.json"):
            try:
                n = int(p.stem.split("-")[-1])
                max_n = max(max_n, n)
            except ValueError:
                continue
    return f"{date_prefix}-{max_n + 1:03d}"
