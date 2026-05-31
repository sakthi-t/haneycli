"""Provider management for Haney.

Handles LLM provider configuration, credential storage,
login/logout, and model listing.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from haney.config import HANEY_DIR


@dataclass
class ProviderInfo:
    """Metadata for a supported LLM provider."""

    name: str
    display_name: str
    api_base: str
    models: list[str]
    env_key: str  # Environment variable name for the API key


# Supported providers with their configurations
PROVIDERS: dict[str, ProviderInfo] = {
    "openai": ProviderInfo(
        name="openai",
        display_name="OpenAI",
        api_base="https://api.openai.com/v1",
        models=[
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4.1-nano",
            "o3",
            "o3-mini",
            "o4-mini",
            "o1",
            "o1-mini",
            "gpt-4-turbo",
            "gpt-4",
        ],
        env_key="OPENAI_API_KEY",
    ),
    "anthropic": ProviderInfo(
        name="anthropic",
        display_name="Anthropic",
        api_base="https://api.anthropic.com",
        models=[
            "claude-opus-4-20250514",
            "claude-sonnet-4-20250514",
            "claude-3.5-sonnet",
            "claude-3.5-haiku",
            "claude-3-opus",
            "claude-3-sonnet",
            "claude-3-haiku",
        ],
        env_key="ANTHROPIC_API_KEY",
    ),
    "deepseek": ProviderInfo(
        name="deepseek",
        display_name="DeepSeek",
        api_base="https://api.deepseek.com",
        models=["deepseek-chat", "deepseek-reasoner"],
        env_key="DEEPSEEK_API_KEY",
    ),
    "gemini": ProviderInfo(
        name="gemini",
        display_name="Google Gemini",
        api_base="https://generativelanguage.googleapis.com/v1beta",
        models=[
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ],
        env_key="GEMINI_API_KEY",
    ),
    "openrouter": ProviderInfo(
        name="openrouter",
        display_name="OpenRouter",
        api_base="https://openrouter.ai/api/v1",
        models=[
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "openai/o3-mini",
            "anthropic/claude-sonnet-4",
            "anthropic/claude-3.5-sonnet",
            "deepseek/deepseek-chat",
            "deepseek/deepseek-reasoner",
            "google/gemini-2.5-flash",
            "google/gemini-2.5-pro",
            "meta-llama/llama-4-maverick",
        ],
        env_key="OPENROUTER_API_KEY",
    ),
    "groq": ProviderInfo(
        name="groq",
        display_name="Groq",
        api_base="https://api.groq.com/openai/v1",
        models=[
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
            "gemma2-9b-it",
            "deepseek-r1-distill-llama-70b",
        ],
        env_key="GROQ_API_KEY",
    ),
}


def get_config_path(cwd: Path | None = None) -> Path:
    """Return the path to the Haney config.json file.

    Args:
        cwd: Working directory. Defaults to current directory.

    Returns:
        Path to .haney/config.json.
    """
    target = (cwd or Path.cwd()) / HANEY_DIR
    return target / "config.json"


def load_config(cwd: Path | None = None) -> dict:
    """Load the Haney configuration from disk.

    Args:
        cwd: Working directory. Defaults to current directory.

    Returns:
        Configuration dictionary. Empty dict if config doesn't exist.
    """
    config_path = get_config_path(cwd)
    if config_path.is_file():
        return json.loads(config_path.read_text(encoding="utf-8"))
    return {}


def save_config(config: dict, cwd: Path | None = None) -> None:
    """Save the Haney configuration to disk.

    Args:
        config: Configuration dictionary to persist.
        cwd: Working directory. Defaults to current directory.
    """
    config_path = get_config_path(cwd)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")


def get_active_provider(cwd: Path | None = None) -> Optional[str]:
    """Return the name of the currently active provider.

    Args:
        cwd: Working directory. Defaults to current directory.

    Returns:
        Provider name string (e.g., 'deepseek'), or None if not set.
    """
    config = load_config(cwd)
    return config.get("active_provider")


def get_api_key(provider_name: str, cwd: Path | None = None) -> Optional[str]:
    """Retrieve the API key for a provider.

    Checks config.json first, then falls back to environment variable.

    Args:
        provider_name: Name of the provider (e.g., 'deepseek').
        cwd: Working directory. Defaults to current directory.

    Returns:
        API key string, or None if not found.
    """
    # 1. Check config.json
    config = load_config(cwd)
    providers = config.get("providers", {})
    if provider_name in providers:
        stored_key = providers[provider_name].get("api_key")
        if stored_key:
            return stored_key

    # 2. Check environment variable
    info = PROVIDERS.get(provider_name)
    if info:
        env_val = os.environ.get(info.env_key)
        if env_val:
            return env_val

    return None


def is_logged_in(provider_name: str | None = None, cwd: Path | None = None) -> bool:
    """Check if the user is logged into a provider.

    Args:
        provider_name: Specific provider to check, or None for active provider.
        cwd: Working directory. Defaults to current directory.

    Returns:
        True if an API key is available for the provider.
    """
    target = provider_name or get_active_provider(cwd)
    if not target:
        return False
    return get_api_key(target, cwd) is not None


def login_provider(
    provider_name: str, api_key: str, set_active: bool = True, cwd: Path | None = None
) -> None:
    """Store credentials for a provider.

    Args:
        provider_name: Name of the provider (e.g., 'deepseek').
        api_key: The API key to store.
        set_active: Whether to set this as the active provider.
        cwd: Working directory. Defaults to current directory.
    """
    config = load_config(cwd)
    if "providers" not in config:
        config["providers"] = {}

    config["providers"][provider_name] = {"api_key": api_key}

    if set_active:
        config["active_provider"] = provider_name

    save_config(config, cwd)


def logout_provider(provider_name: str | None = None, cwd: Path | None = None) -> None:
    """Remove stored credentials for a provider.

    If no provider is specified, logs out the active provider.

    Args:
        provider_name: Name of the provider to log out, or None for active.
        cwd: Working directory. Defaults to current directory.
    """
    config = load_config(cwd)
    target = provider_name or config.get("active_provider")

    if not target:
        return

    # Remove stored credentials
    providers = config.get("providers", {})
    providers.pop(target, None)
    config["providers"] = providers

    # Clear active provider if it matches
    if config.get("active_provider") == target:
        config["active_provider"] = None

    save_config(config, cwd)


def mask_api_key(key: str, visible: int = 8) -> str:
    """Mask an API key for display, showing only the last few characters.

    Args:
        key: The full API key.
        visible: Number of trailing characters to show.

    Returns:
        Masked key string (e.g., 'sk-...abc12345').
    """
    if len(key) <= visible:
        return "*" * len(key)
    prefix = key[:4] if len(key) > 4 else key[:2]
    suffix = key[-visible:]
    return f"{prefix}...{suffix}"


def get_active_model(cwd: Path | None = None) -> str | None:
    """Return the currently active model name.

    Args:
        cwd: Working directory. Defaults to current directory.

    Returns:
        Model name string (e.g., 'deepseek-chat'), or None if not set.
    """
    config = load_config(cwd)
    return config.get("active_model")


def set_active_model(model_name: str, cwd: Path | None = None) -> None:
    """Set the active model in config.

    Args:
        model_name: The model name to set as active.
        cwd: Working directory. Defaults to current directory.
    """
    config = load_config(cwd)
    config["active_model"] = model_name
    save_config(config, cwd)


def get_models_for_provider(
    provider_name: str, cwd: Path | None = None
) -> tuple[list[str], bool, str]:
    """Return models for a provider, fetched live when possible.

    For OpenAI-compatible providers (openai, deepseek, groq, openrouter),
    fetches the live model list from the API when logged in. Falls back to
    the hardcoded defaults if not logged in or on failure.

    For Anthropic and Gemini, uses the curated defaults.

    Args:
        provider_name: Name of the provider.
        cwd: Working directory. Defaults to current directory.

    Returns:
        Tuple of (model_names, fetched_live_bool, source_label).
        source_label is one of: 'live', 'default — login to fetch live',
        or 'default — fetch failed: <reason>'.
    """
    info = PROVIDERS.get(provider_name)
    if not info:
        return [], False, "unknown provider"

    # Providers with OpenAI-compatible /models endpoint
    if provider_name in {"openai", "deepseek", "groq", "openrouter"}:
        api_key = get_api_key(provider_name, cwd)
        if not api_key:
            return list(info.models), False, "default — login to fetch live"

        live, error = _fetch_models_openai_compat(info, api_key)
        if live:
            return live, True, "live"
        return list(info.models), False, f"default — fetch failed: {error}"

    return list(info.models), False, "default — curated list"


def _fetch_models_openai_compat(
    info: ProviderInfo, api_key: str
) -> tuple[list[str] | None, str]:
    """Fetch live model list from an OpenAI-compatible /models endpoint.

    Returns:
        Tuple of (model_ids_or_None, error_message_or_empty).
    """
    import httpx
    try:
        resp = httpx.get(
            f"{info.api_base}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            raw = data.get("data", [])
            models = [m["id"] for m in raw if m.get("id")]
            if models:
                return models, ""
            return None, "empty response from API"
        if resp.status_code == 401:
            return None, "invalid API key (401)"
        if resp.status_code == 429:
            return None, "rate limited (429)"
        return None, f"HTTP {resp.status_code}"
    except httpx.ConnectError:
        return None, "network error — cannot reach API"
    except httpx.TimeoutException:
        return None, "API request timed out"
    except Exception as exc:
        return None, str(exc)[:80]


def is_web_search_enabled(cwd: Path | None = None) -> bool:
    """Check if web search is enabled in config.

    Defaults to True if not explicitly set.

    Args:
        cwd: Working directory. Defaults to current directory.

    Returns:
        True if web_search is enabled.
    """
    config = load_config(cwd)
    return config.get("web_search", True)


def set_web_search_enabled(enabled: bool, cwd: Path | None = None) -> None:
    """Enable or disable web search in config.

    Args:
        enabled: True to enable, False to disable.
        cwd: Working directory. Defaults to current directory.
    """
    config = load_config(cwd)
    config["web_search"] = enabled
    save_config(config, cwd)
