"""Configuration bootstrap for Haney.

Defines every configurable key with its default value.
At startup, missing keys are auto-populated into config.json.
Supports null for "no limit" on numeric settings.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from haney.providers import load_config, save_config

# ── Master config schema ──────────────────────────────────────────────────────
# Every key Haney reads from config.json is defined here.
# null means "unlimited" / "no constraint".

CONFIG_SCHEMA: dict[str, Any] = {
    # ── Provider ──────────────────────────────────────────────
    "active_provider": None,
    "active_model": None,
    "providers": {},

    # ── Modes ─────────────────────────────────────────────────
    "mode": "plan",
    "thinking_mode": "medium",
    "permission_mode": "ask",

    # ── UI ───────────────────────────────────────────────────
    "ui": {
        "sticky_input": True,
        "input_bottom_padding": 2,
        "show_status_bar": True,
    },

    # ── Approval (legacy) ────────────────────────────────────

    # ── Search ────────────────────────────────────────────────
    "web_search": True,
    "search_provider": "exa",
    "search": {},

    # ── Limits (null = unlimited) ─────────────────────────────
    "max_tool_calls": 20,
    "max_attachment_tokens": 10000,
    "max_context_tokens": None,

    # ── Approval ──────────────────────────────────────────────
    # "write_only" — confirm only write/delete/shell tools
    # "all"        — confirm every tool including reads
    # "none"       — never confirm (dangerous)
    "approval_mode": "write_only",

    # ── Comments (preserved for readability) ──────────────────
    "_comment": (
        "Haney configuration. Set API keys via /login <provider>. "
        "Set EXA_API_KEY via /login exa or the env var."
    ),
    "_exa_comment": "EXA_API_KEY can be set via /login exa or the EXA_API_KEY env var.",
}


def bootstrap_config(cwd: Path | None = None, console=None) -> dict:
    """Ensure config.json has every key from the schema.

    Missing keys are added with their defaults. Existing values
    are never overwritten. Informs the user of newly added keys.

    Args:
        cwd: Working directory.
        console: Optional Rich Console for user feedback.

    Returns:
        The complete config dict.
    """
    config = load_config(cwd)
    added: list[str] = []

    for key, default in CONFIG_SCHEMA.items():
        if key not in config:
            config[key] = default
            added.append(key)

    if added and console:
        console.print(
            f"[dim]Config bootstrapped: added {', '.join(sorted(added))}[/dim]"
        )

    if added:
        save_config(config, cwd)

    return config
