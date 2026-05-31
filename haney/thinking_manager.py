"""Thinking mode manager for Haney.

Provides a unified thinking-mode abstraction across providers.
Users set low/medium/high/off — Haney translates to provider-
specific parameters internally.
"""

from __future__ import annotations

from pathlib import Path

from haney.providers import load_config, save_config

# ── Mode definitions ──────────────────────────────────────────────────────────

VALID_MODES = {"off", "low", "medium", "high"}
DEFAULT_MODE = "medium"


def get_thinking_mode(cwd: Path | None = None) -> str:
    """Return the current thinking mode.

    Args:
        cwd: Working directory.

    Returns:
        One of: off, low, medium, high. Defaults to medium.
    """
    config = load_config(cwd)
    mode = config.get("thinking_mode", DEFAULT_MODE)
    return mode if mode in VALID_MODES else DEFAULT_MODE


def set_thinking_mode(mode: str, cwd: Path | None = None) -> None:
    """Set the thinking mode in config.json.

    Args:
        mode: One of off, low, medium, high.
        cwd: Working directory.

    Raises:
        ValueError: If mode is invalid.
    """
    mode = mode.lower().strip()
    if mode not in VALID_MODES:
        raise ValueError(
            f"Invalid thinking mode: '{mode}'. "
            f"Use one of: {', '.join(sorted(VALID_MODES))}"
        )
    config = load_config(cwd)
    config["thinking_mode"] = mode
    save_config(config, cwd)


# ── Provider mappings ─────────────────────────────────────────────────────────

def get_completion_params(
    provider: str, mode: str
) -> dict:
    """Return litellm completion params for the given provider + mode.

    Args:
        provider: Provider name (openai, deepseek, etc.).
        mode: Thinking mode (off, low, medium, high).

    Returns:
        Dict of extra kwargs for litellm.completion().
    """
    params: dict = {}

    if mode == "off":
        params["temperature"] = 0.0

    elif mode == "low":
        params["temperature"] = 0.2

    elif mode == "medium":
        # Default — no special params
        pass

    elif mode == "high":
        if provider == "openai":
            params["reasoning_effort"] = "high"
        elif provider == "anthropic":
            params["thinking"] = {"type": "enabled", "budget_tokens": 4000}
        # deepseek, gemini, groq, openrouter: no special high-mode params

    return params
