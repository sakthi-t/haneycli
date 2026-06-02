"""Command handlers for Haney slash-commands."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.text import Text

from haney.config import COMMAND_PREFIX, HANEY_DIR, VERSION
from haney.providers import (
    PROVIDERS,
    ProviderInfo,
    get_active_provider,
    get_api_key,
    get_active_model,
    get_models_for_provider,
    is_logged_in,
    login_provider,
    logout_provider,
    mask_api_key,
    set_active_model,
    is_web_search_enabled,
)
from haney.search import (
    get_exa_api_key,
    is_search_logged_in,
    login_search,
    logout_search,
)
from haney.project_context import ProjectContextManager
from haney.thinking_manager import (
    get_thinking_mode,
    set_thinking_mode,
    VALID_MODES,
)
from haney.mode_manager import get_mode, set_mode, is_edit_mode
from haney.permission_manager import (
    get_permission_mode,
    set_permission_mode,
    VALID_MODES as PERMISSION_MODES,
    PermissionManager,
)
from haney.mcp.server_manager import MCPServerManager
from haney.mcp.github_oauth import GitHubOAuth, GitHubOAuthError
from haney.mcp.server_configs import get_server_config, MCP_SERVERS
from haney.providers import load_config, save_config

if TYPE_CHECKING:
    from haney.llm import ChatSession
    from haney.session_manager import SessionManager


@dataclass
class Command:
    """Represents a slash-command with its handler and description."""

    name: str
    description: str
    handler: Callable[[Console, list[str]], None]


# ── Phase 1 Commands ──────────────────────────────────────────────────────────

def cmd_help(console: Console, args: list[str]) -> None:
    """Display available commands.

    Args:
        console: Rich Console instance for output.
        args: Additional arguments (unused).
    """
    commands: list[tuple[str, str]] = [
        # Phase 1
        ("/help", "Display this help message"),
        ("/version", "Show Haney version and project info"),
        ("/clear", "Clear the terminal screen"),
        ("/exit", "Exit Haney gracefully"),
        # Phase 2 — Provider Management
        ("/login <provider>", "Connect an LLM provider or Exa search"),
        ("/logout [provider]", "Disconnect from a provider"),
        ("/models [provider]", "List all available models"),
        ("/model [name]", "Show or set the active model"),
        ("/provider", "Show current provider status"),
        # Phase 5 — Project Awareness
        ("/project", "Show project status and loaded files"),
        ("/reload", "Re-scan project files"),
        ("/context", "Show loaded context details"),
        ("/init", "Generate starter project-awareness files"),
        # Phase 7 — Safe Tools
        ("/trash", "Show files in trash"),
        ("/restore <file>", "Restore file from trash"),
        # Phase 8 — Session Management
        ("/history", "Show recent sessions"),
        ("/session", "Current session info"),
        ("/stats", "Token and cost metrics"),
        # Phase 10 & 11 — Memory & Compact
        ("/remember <text>", "Append to memory.md"),
        ("/summary", "Show project summary"),
        ("/compact", "Compact conversation + update summary"),
        # Phase 12 & 13 — Thinking Modes & Status
        ("/think [off|low|medium|high]", "Show/set thinking mode"),
        ("/status", "Show full runtime status"),
        # Phase 14 — Plan / Edit Mode
        ("/plan", "Switch to PLAN mode (discussion only)"),
        ("/edit", "Switch to EDIT mode (tools enabled)"),
        ("/mode", "Show current execution mode"),
        # Permission
        ("/permission [ask|save|auto]", "Set approval mode"),
        # MCP
        ("/mcp login <server>", "Authenticate with an MCP server"),
        ("/mcp logout <server>", "Clear MCP credentials"),
        ("/mcp connect <server>", "Connect to an MCP server"),
        ("/mcp disconnect [server]", "Disconnect MCP server(s)"),
        ("/mcp status", "Show MCP connection status"),
        ("/mcp servers", "List available MCP servers"),
    ]

    table = Table(title="Available Commands", border_style="blue", title_justify="left")
    table.add_column("Command", style="bold cyan", no_wrap=True)
    table.add_column("Description", style="dim")

    for name, desc in commands:
        table.add_row(name, desc)

    console.print(table)
    console.print(
        "\n[dim]Supported providers: openai, anthropic, deepseek, gemini, openrouter, groq, exa[/dim]"
    )
    console.print(
        "[dim]Attach files with @filename in chat messages. Use /attachments to view.[/dim]"
    )


def cmd_version(console: Console, args: list[str]) -> None:
    """Display the current Haney version.

    Args:
        console: Rich Console instance for output.
        args: Additional arguments (unused).
    """
    version_text = f"Haney v{VERSION}"
    panel = Panel(version_text, border_style="yellow", title="Version", title_align="left")
    console.print(panel)


def cmd_clear(console: Console, args: list[str]) -> None:
    """Clear the terminal screen.

    Also clears file attachments if a session is active.
    Note: session.clear() is called from dispatch(),
    this handler only clears the screen.

    Args:
        console: Rich Console instance for output.
        args: Additional arguments (unused).
    """
    console.clear()


def cmd_exit(console: Console, args: list[str]) -> None:
    """Exit Haney gracefully.

    Args:
        console: Rich Console instance for output.
        args: Additional arguments (unused).
    """
    console.print("\n[dim]Goodbye! Haney is napping now. :3[/dim]")
    sys.exit(0)


# ── Phase 2 Commands: Provider Management ─────────────────────────────────────

def _list_providers(console: Console) -> None:
    """Print a table of supported providers."""
    table = Table(title="Supported Providers", border_style="cyan", title_justify="left")
    table.add_column("Provider", style="bold green", no_wrap=True)
    table.add_column("Command", style="cyan")
    table.add_column("Models", style="dim")

    for info in PROVIDERS.values():
        model_preview = ", ".join(info.models[:3])
        if len(info.models) > 3:
            model_preview += f", +{len(info.models) - 3} more"
        table.add_row(info.display_name, f"/login {info.name}", model_preview)

    # Add Exa (search provider) as a special row
    table.add_row(
        "[bold]Exa Search[/bold]",
        "/login exa",
        "[dim]Web search enrichment[/dim]",
    )

    console.print(table)


def cmd_login(console: Console, args: list[str]) -> None:
    """Login to an LLM provider.

    Usage: /login <provider>
    Example: /login deepseek

    Prompts for the API key (masked input), stores it locally,
    and sets the provider as active.

    Args:
        console: Rich Console instance for output.
        args: Command arguments (provider name expected).
    """
    if not args:
        console.print("[yellow]Usage:[/yellow] /login <provider>")
        console.print()
        _list_providers(console)
        return

    provider_name = args[0].lower().strip()

    # ── Exa (search provider) ──────────────────────────────────────
    if provider_name == "exa":
        _cmd_login_exa(console)
        return

    # ── LLM providers ──────────────────────────────────────────────
    if provider_name not in PROVIDERS:
        console.print(f"[red]Unknown provider:[/red] {provider_name}")
        console.print()
        _list_providers(console)
        return

    info = PROVIDERS[provider_name]

    # Check if already logged in
    existing_key = get_api_key(provider_name)
    if existing_key:
        console.print(
            f"[yellow]Already logged into {info.display_name} "
            f"(key: {mask_api_key(existing_key)})[/yellow]"
        )
        if not Confirm.ask("Re-enter API key?", default=False):
            console.print("[dim]Login cancelled. Keeping existing credentials.[/dim]")
            return

    # Check environment variable
    env_key = os.environ.get(info.env_key)
    if env_key and not existing_key:
        masked = mask_api_key(env_key)
        console.print(f"[dim]Found {info.env_key} in environment ({masked})[/dim]")
        use_env = Confirm.ask(
            f"Use this environment key for {info.display_name}?", default=True
        )
        if use_env:
            login_provider(provider_name, env_key)
            # Auto-select first model if none set
            if not get_active_model() and info.models:
                set_active_model(info.models[0])
            console.print(
                f"\n[bold green]✓[/bold green] Logged into [bold]{info.display_name}[/bold] "
                f"(key from {info.env_key})"
            )
            console.print(f"[dim]Active provider: {info.display_name}[/dim]")
            if info.models:
                console.print(f"[dim]Active model: {info.models[0]}[/dim]")
            return

    # Prompt for API key
    console.print(f"\n[bold]Connecting to {info.display_name}...[/bold]")
    console.print(f"[dim]API Base: {info.api_base}[/dim]")
    console.print()

    api_key = Prompt.ask(
        f"Enter your {info.display_name} API key",
        password=True,
    )

    if not api_key or not api_key.strip():
        console.print("[red]No API key provided. Login cancelled.[/red]")
        return

    login_provider(provider_name, api_key.strip())

    # Auto-select first model if none set
    if not get_active_model() and info.models:
        set_active_model(info.models[0])

    console.print()
    console.print(
        f"[bold green]✓[/bold green] Logged into [bold]{info.display_name}[/bold]"
    )
    console.print(f"[dim]Credentials stored in .haney/config.json[/dim]")
    console.print(f"[dim]Active provider: {info.display_name}[/dim]")
    if info.models:
        console.print(f"[dim]Active model: {info.models[0]}[/dim]")


def _cmd_login_exa(console: Console) -> None:
    """Handle /login exa — prompt for Exa API key."""
    existing = get_exa_api_key()
    if existing:
        console.print(
            f"[yellow]Already logged into Exa "
            f"(key: {mask_api_key(existing)})[/yellow]"
        )
        if not Confirm.ask("Re-enter API key?", default=False):
            console.print("[dim]Login cancelled. Keeping existing credentials.[/dim]")
            return

    console.print("\n[bold]Connecting to Exa Search…[/bold]")
    console.print("[dim]Web search will automatically enrich answers when needed.[/dim]")
    console.print()

    api_key = Prompt.ask("Enter your Exa API key", password=True)

    if not api_key or not api_key.strip():
        console.print("[red]No API key provided. Login cancelled.[/red]")
        return

    login_search(api_key.strip())

    console.print()
    console.print("[bold green]✓[/bold green] Logged into [bold]Exa Search[/bold]")
    console.print("[dim]Key stored in .haney/config.json[/dim]")
    console.print("[dim]Search will run automatically when needed.[/dim]")


def cmd_logout(console: Console, args: list[str]) -> None:
    """Logout from the current provider.

    Usage: /logout [provider]
    If no provider is specified, logs out the active provider.

    Args:
        console: Rich Console instance for output.
        args: Command arguments (optional provider name).
    """
    active = get_active_provider()

    provider_name = args[0].lower().strip() if args else active

    # ── Exa (search provider) ──────────────────────────────────────
    if provider_name == "exa":
        if not is_search_logged_in():
            console.print("[yellow]Not logged into Exa.[/yellow]")
            return
        logout_search()
        console.print("[bold green]✓[/bold green] Logged out from [bold]Exa Search[/bold]")
        console.print("[dim]API key removed from .haney/config.json[/dim]")
        return

    # ── LLM providers ──────────────────────────────────────────────
    if not provider_name:
        console.print("[yellow]No provider is currently active.[/yellow]")
        console.print("[dim]Use /login <provider> to connect.[/dim]")
        return

    info = PROVIDERS.get(provider_name)
    display = info.display_name if info else provider_name

    if not is_logged_in(provider_name):
        console.print(f"[yellow]Not logged into {display}.[/yellow]")
        return

    logout_provider(provider_name)

    console.print(
        f"[bold green]✓[/bold green] Logged out from [bold]{display}[/bold]"
    )
    console.print("[dim]Credentials removed from local storage.[/dim]")
    if provider_name == active:
        console.print("[dim]No active provider set.[/dim]")


def cmd_models(console: Console, args: list[str]) -> None:
    """List ALL available models for a provider.

    For OpenAI-compatible providers, fetches the live model list
    from the API when logged in. Falls back to curated defaults otherwise.

    Usage: /models [provider]

    Args:
        console: Rich Console instance for output.
        args: Command arguments (optional provider name).
    """
    active = get_active_provider()
    provider_name = args[0].lower().strip() if args else active

    if not provider_name:
        console.print("[yellow]No active provider.[/yellow]")
        console.print("[dim]Use /login <provider> to connect.[/dim]")
        console.print()
        _list_providers(console)
        return

    info = PROVIDERS.get(provider_name)
    if not info:
        console.print(f"[red]Unknown provider:[/red] {provider_name}")
        return

    logged_in = is_logged_in(provider_name)
    models, live_fetched, source_label = get_models_for_provider(provider_name)
    current_model = get_active_model()

    if live_fetched:
        source = "[dim](live)[/dim]"
    elif "login" in source_label:
        source = f"[dim]({source_label})[/dim]"
    else:
        source = f"[dim]({source_label})[/dim]"

    table = Table(
        title=f"Models — {info.display_name} ({len(models)} total) {source}",
        border_style="magenta",
        title_justify="left",
    )
    table.add_column("#", style="dim", no_wrap=True, width=4)
    table.add_column("Model", style="bold cyan")
    table.add_column("Active", style="dim", width=8)
    table.add_column("Status", style="dim")

    status = "[green]available[/green]" if logged_in else "[yellow]login required[/yellow]"

    for i, model in enumerate(models, 1):
        is_active = "[bold yellow]★[/bold yellow]" if model == current_model else ""
        table.add_row(str(i), model, is_active, status)

    console.print(table)

    if not logged_in:
        console.print(
            f"\n[dim]Login to fetch live models. Use /login {provider_name} to connect.[/dim]"
        )
    else:
        console.print(
            f"\n[dim]Use /model <name> to switch. Current: [bold]{current_model or 'none'}[/bold][/dim]"
        )


def cmd_model(console: Console, args: list[str]) -> None:
    """Show or set the active model.

    Usage:
        /model          — Show the active model and list available
        /model <name>   — Set the active model

    Args:
        console: Rich Console instance for output.
        args: Command arguments (optional model name).
    """
    provider = get_active_provider()

    if not provider:
        console.print("[yellow]No active provider set.[/yellow]")
        console.print("[dim]Use /login <provider> to connect first, then /model <name> to pick a model.[/dim]")
        console.print("[dim]Type /help to see all available commands.[/dim]")
        return

    info = PROVIDERS.get(provider)
    available_models, _live, _source = get_models_for_provider(provider)

    if not args:
        # Show current model
        current = get_active_model()
        think = get_thinking_mode()
        search = is_web_search_enabled()

        table = Table(title="Model Configuration", border_style="cyan", title_justify="left")
        table.add_column("Setting", style="bold", no_wrap=True)
        table.add_column("Value", style="cyan")
        table.add_row("Provider", info.display_name if info else provider)
        table.add_row("Model", current or "[dim]not set[/dim]")
        table.add_row("Thinking", think)
        table.add_row("Search", "[green]enabled[/green]" if search else "[yellow]disabled[/yellow]")
        console.print(table)

        if available_models:
            console.print(f"\n[dim]Available models ({len(available_models)}):[/dim]")
            for m in available_models:
                marker = " [bold yellow]★[/bold yellow]" if m == current else ""
                console.print(f"  [cyan]{m}[/cyan]{marker}")

        console.print("\n[dim]Usage: /model <name>  —  Type /models for a detailed table  —  /help for all commands[/dim]")
        return

    # Set model
    model_name = args[0].strip()

    if model_name not in available_models:
        console.print(f"[red]Unknown model:[/red] {model_name}")
        console.print(f"[dim]Available models for {info.display_name if info else provider}:[/dim]")
        for m in available_models:
            console.print(f"  [cyan]{m}[/cyan]")
        console.print(f"\n[dim]Use /models to see all models in a table. Type /help for all commands.[/dim]")
        return

    set_active_model(model_name)

    console.print(
        f"[bold green]✓[/bold green] Active model set to [bold cyan]{model_name}[/bold cyan] "
        f"([dim]{info.display_name if info else provider}[/dim])"
    )


def cmd_provider(console: Console, args: list[str]) -> None:
    """Show current provider status.

    Usage: /provider

    Displays the active provider, login status, active model, and masked API key.

    Args:
        console: Rich Console instance for output.
        args: Additional arguments (unused).
    """
    active = get_active_provider()

    if not active:
        console.print("[yellow]No active provider.[/yellow]")
        console.print("[dim]Use /login <provider> to connect.[/dim]")
        console.print()
        _list_providers(console)
        return

    info = PROVIDERS.get(active)
    logged_in = is_logged_in(active)
    current_model = get_active_model()

    table = Table(
        title="Provider Status",
        border_style="green" if logged_in else "yellow",
        title_justify="left",
    )
    table.add_column("Setting", style="bold", no_wrap=True)
    table.add_column("Value", style="cyan")

    table.add_row("Provider", info.display_name if info else active)
    table.add_row("API Base", info.api_base if info else "N/A")
    table.add_row(
        "Status",
        "[green]Connected[/green]" if logged_in else "[red]Not logged in[/red]",
    )

    if logged_in:
        key = get_api_key(active)
        if key:
            table.add_row("API Key", mask_api_key(key))
    else:
        table.add_row("API Key", "[dim]Not set[/dim]")

    table.add_row("Active Model", current_model or "[dim]Not set[/dim]")
    table.add_row("Models Available", str(len(info.models)) if info else "N/A")

    console.print(table)


# ── Phase 5 Commands: Project Awareness ───────────────────────────────────────

# Module-level context manager — initialised by chat.py, shared with commands
_ctx_manager: ProjectContextManager | None = None


def set_context_manager(ctx: ProjectContextManager) -> None:
    """Set the shared project context manager.

    Called once by chat.py when the session starts.
    """
    global _ctx_manager
    _ctx_manager = ctx


def _get_ctx() -> ProjectContextManager:
    """Return the shared context manager, creating one if needed."""
    global _ctx_manager
    if _ctx_manager is None:
        _ctx_manager = ProjectContextManager()
    return _ctx_manager


def cmd_project(console: Console, args: list[str]) -> None:
    """Display current project information.

    Shows project name, awareness status, loaded/missing files,
    context size, and last reload time. Never fails.
    """
    ctx = _get_ctx()
    high = ctx.high_priority_files
    missing = ctx.missing_awareness_files
    all_loaded = ctx.loaded_files
    tokens = ctx.total_tokens
    ago = ctx.last_reload_seconds

    table = Table(
        title=f"Project Status — {ctx.project_name}",
        border_style="green" if ctx.has_any_awareness else "yellow",
        title_justify="left",
    )
    table.add_column("Setting", style="bold", no_wrap=True)
    table.add_column("Value", style="cyan")

    table.add_row("Project Name", ctx.project_name)
    table.add_row(
        "Project Awareness",
        "[green]Enabled[/green]" if ctx.has_any_awareness else "[yellow]Limited[/yellow]",
    )
    table.add_row(
        "Context Size",
        f"~{tokens} tokens" if tokens else "[dim]empty[/dim]",
    )

    if ago < 60:
        ago_str = f"{ago:.0f}s ago"
    elif ago < 3600:
        ago_str = f"{ago / 60:.0f}m ago"
    else:
        ago_str = f"{ago / 3600:.1f}h ago"
    table.add_row("Last Reload", ago_str)

    console.print(table)

    # Loaded awareness files
    if high:
        console.print("\n[bold]Loaded Files:[/bold]")
        for f in high:
            kb = f.size_bytes / 1024
            console.print(f"  [green]✓[/green] {f.name} [dim]({kb:.1f} KB)[/dim]")

    # Missing awareness files
    if missing:
        console.print("\n[bold yellow]Missing Files:[/bold yellow]")
        for name in missing:
            console.print(f"  [yellow]⚠[/yellow] {name}")
        if not high and not missing:
            pass
        elif missing and not high:
            console.print("\n[dim]Suggestion: Run /init to generate project files.[/dim]")

    # Detected source files
    sources = [f for f in all_loaded if f.priority == "source"]
    if sources:
        console.print(f"\n[bold]Detected Source Files:[/bold] [dim]({len(sources)} files)[/dim]")
        shown = sources[:8]
        for f in shown:
            console.print(f"  [dim]  {f.name}[/dim]")
        if len(sources) > 8:
            console.print(f"  [dim]  … and {len(sources) - 8} more[/dim]")

    if not high and not sources:
        console.print("\n[dim]No project files detected. Run /init to create awareness files.[/dim]")


def cmd_reload(console: Console, args: list[str]) -> None:
    """Re-scan and reload all project files.

    Refreshes internal context, recalculates token estimates,
    and updates the file cache.
    """
    console.print("[bold]Reloading project…[/bold]\n")

    ctx = _get_ctx()
    ctx.reload()

    high = ctx.high_priority_files
    missing = ctx.missing_awareness_files

    for f in high:
        console.print(f"  [green]✓[/green] {f.name}")

    for name in missing:
        console.print(f"  [yellow]⚠[/yellow] {name} [dim](not found)[/dim]")

    if not high and not missing:
        console.print("  [dim]No project awareness files found.[/dim]")

    tokens = ctx.total_tokens
    console.print(f"\n[bold green]Project context refreshed.[/bold green]")
    if tokens:
        console.print(f"[dim]Context size: ~{tokens} tokens[/dim]")


def cmd_context(console: Console, args: list[str]) -> None:
    """Display loaded context details with token estimates.

    Shows file sizes, token counts, and overall context health.
    """
    ctx = _get_ctx()
    all_loaded = ctx.loaded_files

    if not all_loaded:
        console.print("[yellow]No project files loaded.[/yellow]")
        console.print("[dim]Run /init to create awareness files, then /reload to scan.[/dim]")
        return

    table = Table(
        title=f"Loaded Context — {ctx.project_name}",
        border_style="blue",
        title_justify="left",
    )
    table.add_column("File", style="bold cyan", no_wrap=True)
    table.add_column("Size", style="dim", justify="right")
    table.add_column("Est. Tokens", style="dim", justify="right")
    table.add_column("Priority", style="dim")

    total_size = 0
    total_tokens = 0

    for f in all_loaded:
        kb = f.size_bytes / 1024
        tokens = ctx.estimate_tokens(f.content)
        total_size += f.size_bytes
        total_tokens += tokens
        prio_label = {
            "high": "[green]high[/green]",
            "medium": "[yellow]medium[/yellow]",
            "source": "[dim]source[/dim]",
        }.get(f.priority, f.priority)
        table.add_row(f.name, f"{kb:.1f} KB", str(tokens), prio_label)

    table.add_section()
    table.add_row(
        "[bold]Total[/bold]",
        f"[bold]{total_size / 1024:.1f} KB[/bold]",
        f"[bold]{total_tokens}[/bold]",
        "",
    )

    console.print(table)

    # Health indicator
    if total_tokens < 4000:
        health = "[green]Healthy[/green]"
    elif total_tokens < 8000:
        health = "[yellow]Moderate[/yellow]"
    else:
        health = "[red]Large — consider /compact[/red]"

    console.print(f"\nContext Status: {health}")


def cmd_init(console: Console, args: list[str]) -> None:
    """Generate starter project-awareness files.

    Creates plan.md, memory.md, summary.md, and tasks.md.
    Only creates files that do not already exist — never
    overwrites user content.
    """
    ctx = _get_ctx()
    created = ctx.init_files()

    if not created:
        console.print("[yellow]All project-awareness files already exist.[/yellow]")
        console.print("[dim]Nothing to create. Files present:[/dim]")
        for f in ctx.high_priority_files:
            console.print(f"  [green]✓[/green] {f.name}")
        return

    for name in created:
        console.print(f"  [green]✓[/green] Created {name}")

    console.print(f"\n[dim]Project files created in {ctx.cwd}/[/dim]")
    console.print("[dim]Run /reload to load them into context.[/dim]")


# ── Phase 7 Commands: Trash & Restore ─────────────────────────────────────────

def cmd_trash(console: Console, args: list[str]) -> None:
    """Show files in .haney/trash/."""
    from haney.tools.file_tools import list_trash
    result = list_trash(Path.cwd())
    if result.success:
        console.print(Panel(
            result.content_preview or result.message,
            title="Trash",
            border_style="yellow",
            title_align="left",
        ))
        console.print("[dim]Use /restore <filename> to recover a file.[/dim]")
    else:
        console.print(f"[red]{result.message}[/red]")


def cmd_restore(console: Console, args: list[str]) -> None:
    """Restore a file from .haney/trash/.

    Usage: /restore <filename>
    """
    from haney.tools.file_tools import restore_file
    if not args:
        console.print("[yellow]Usage:[/yellow] /restore <filename>")
        console.print("[dim]Use /trash to see files available for restore.[/dim]")
        return

    filename = args[0].strip()
    result = restore_file(Path.cwd(), filename)
    if result.success:
        console.print(f"[bold green]✓[/bold green] {result.message}")
    else:
        console.print(f"[red]{result.message}[/red]")


# ── Phase 8 Commands: Session Management ──────────────────────────────────────

# Module-level session manager — set by chat.py
_session_mgr: "SessionManager | None" = None


def set_session_manager(mgr: "SessionManager") -> None:
    """Set the shared session manager. Called by chat.py."""
    global _session_mgr
    _session_mgr = mgr


def cmd_history(console: Console, args: list[str]) -> None:
    """Show recent sessions (historical records only — not loaded)."""
    from haney.session_manager import SessionManager
    sessions = SessionManager.list_sessions()

    if not sessions:
        console.print("[dim]No previous sessions found.[/dim]")
        return

    table = Table(
        title=f"Recent Sessions ({len(sessions)} total)",
        border_style="blue",
        title_justify="left",
    )
    table.add_column("Session ID", style="bold cyan", no_wrap=True)
    table.add_column("Provider", style="dim")
    table.add_column("Model", style="dim")
    table.add_column("Msgs", justify="right")
    table.add_column("Cost", justify="right")

    for s in sessions[:20]:
        table.add_row(
            s["session_id"],
            s["provider"],
            s["model"],
            str(s["messages"]),
            f"${s['cost']:.4f}",
        )

    console.print(table)
    console.print("[dim]Sessions are historical records only — not loaded into context.[/dim]")


def cmd_session(console: Console, args: list[str]) -> None:
    """Display current session information."""
    global _session_mgr
    if _session_mgr is None:
        console.print("[yellow]No active session.[/yellow]")
        return

    mgr = _session_mgr

    table = Table(
        title=f"Current Session — {mgr.session_id}",
        border_style="green",
        title_justify="left",
    )
    table.add_column("Setting", style="bold", no_wrap=True)
    table.add_column("Value", style="cyan")

    table.add_row("Session ID", mgr.session_id)
    table.add_row("Provider", mgr.provider)
    table.add_row("Model", mgr.model)
    table.add_row("Started", mgr.started_at_display)
    table.add_row("Messages", str(mgr.message_count))
    table.add_row("API Calls", str(mgr.api_calls))
    table.add_row("Cost", f"${mgr.cost:.4f}")

    console.print(table)


def cmd_stats(console: Console, args: list[str]) -> None:
    """Display token and cost metrics for the current session."""
    global _session_mgr
    if _session_mgr is None:
        console.print("[yellow]No active session.[/yellow]")
        return

    mgr = _session_mgr

    table = Table(
        title="Session Stats",
        border_style="cyan",
        title_justify="left",
    )
    table.add_column("Metric", style="bold", no_wrap=True)
    table.add_column("Value", style="cyan", justify="right")

    table.add_row("Input Tokens", f"{mgr.input_tokens:,}")
    table.add_row("Output Tokens", f"{mgr.output_tokens:,}")
    table.add_row("Total Tokens", f"{mgr.total_tokens:,}")
    table.add_row("API Calls", str(mgr.api_calls))
    table.add_row("Cost", f"${mgr.cost:.4f}")

    if mgr.api_calls > 0:
        avg_in = mgr.input_tokens // mgr.api_calls
        avg_out = mgr.output_tokens // mgr.api_calls
        table.add_section()
        table.add_row("Avg Input/Call", f"{avg_in:,}")
        table.add_row("Avg Output/Call", f"{avg_out:,}")

    console.print(table)


# ── Phase 10 & 11 Commands: Memory, Summary, Compact ──────────────────────────


def cmd_remember(console: Console, args: list[str]) -> None:
    """Append information to memory.md.

    Usage: /remember <text>
    """
    if not args:
        console.print("[yellow]Usage:[/yellow] /remember <information to save>")
        console.print("[dim]Example: /remember Use FastAPI for this project[/dim]")
        return

    text = " ".join(args).strip()
    memory_path = Path.cwd() / ".haney" / "memory.md"

    try:
        if memory_path.is_file():
            existing = memory_path.read_text(encoding="utf-8").rstrip()
            content = existing + "\n\n* " + text + "\n"
        else:
            content = "# Project Memory\n\n* " + text + "\n"

        memory_path.write_text(content, encoding="utf-8")
        console.print(f"[bold green]✓[/bold green] Added to [bold]memory.md[/bold]:")
        console.print(f"  [cyan]{text}[/cyan]")
        console.print("\n[dim]Run /reload to refresh project context.[/dim]")
    except OSError as exc:
        console.print(f"[red]Cannot write memory.md: {exc}[/red]")


def cmd_summary(console: Console, args: list[str]) -> None:
    """Display current summary.md content. No LLM call required."""
    summary_path = Path.cwd() / ".haney" / "summary.md"

    if not summary_path.is_file():
        console.print("[yellow]No summary available.[/yellow]")
        console.print("[dim]Run /compact to generate one.[/dim]")
        return

    try:
        content = summary_path.read_text(encoding="utf-8")
    except OSError:
        console.print("[red]Cannot read summary.md[/red]")
        return

    console.print(Panel(
        content.strip(),
        title="Project Summary",
        border_style="cyan",
        title_align="left",
    ))


def cmd_compact(console: Console, session: "ChatSession") -> None:
    """Compact conversation using an LLM call and update summary.md.

    Gathers conversation history, project context, and memory,
    sends to the active model for summarisation, writes to
    summary.md, and truncates old messages.

    Args:
        console: Rich Console instance.
        session: Active ChatSession for LLM call and message truncation.
    """
    import litellm
    from haney.providers import get_active_provider, get_api_key, get_active_model
    from haney.project_context import ProjectContextManager

    provider = get_active_provider()
    if not provider:
        console.print("[red]No active provider. Use /login first.[/red]")
        return

    model = get_active_model()
    if not model:
        console.print("[red]No active model. Use /model first.[/red]")
        return

    api_key = get_api_key(provider)
    if not api_key:
        console.print(f"[red]No API key for {provider}.[/red]")
        return

    # Gather context
    ctx = ProjectContextManager()
    ctx.reload()

    memory = ""
    mem_path = Path.cwd() / ".haney" / "memory.md"
    if mem_path.is_file():
        memory = mem_path.read_text(encoding="utf-8")

    old_summary = ""
    sum_path = Path.cwd() / ".haney" / "summary.md"
    if sum_path.is_file():
        old_summary = sum_path.read_text(encoding="utf-8")

    # Build conversation transcript
    conversation = ""
    for m in session.messages[-40:]:  # last 40 messages max
        role = m.get("role", "?")
        content = m.get("content", "")[:1000]
        conversation += f"**{role}:** {content}\n\n"

    # Token estimate before
    tokens_before = sum(len(m.get("content", "")) for m in session.messages) // 4

    console.print("[bold cyan]Compacting conversation…[/bold cyan]\n")

    prompt = f"""You are generating a concise project summary for Haney CLI.

## Project Memory
{memory if memory else '(none)'}

## Previous Summary
{old_summary if old_summary else '(none)'}

## Recent Conversation
{conversation}

---

Generate a concise project summary covering:
- Completed work
- Important decisions
- Current architecture
- Open tasks
- Known issues

Keep under 1000 words. Use Markdown."""

    try:
        response = litellm.completion(
            model=f"{provider}/{model}",
            messages=[{"role": "user", "content": prompt}],
            api_key=api_key,
        )
        summary_text = response.choices[0].message.content or ""
    except Exception as exc:
        console.print(f"[red]LLM call failed: {exc}[/red]")
        return

    # Write summary
    try:
        sum_path.write_text(summary_text.strip(), encoding="utf-8")
        console.print("[green]✓[/green] [bold]summary.md updated[/bold]")
    except OSError as exc:
        console.print(f"[red]Cannot write summary.md: {exc}[/red]")
        return

    # Compact session: keep system context + last 10 messages
    before_count = len(session.messages)
    if before_count > 20:
        # Keep last 10 messages (5 user-assistant pairs)
        session.messages = session.messages[-10:]
        after_count = len(session.messages)
    else:
        after_count = before_count

    # Reload project context to pick up new summary
    ctx.reload()

    # Metrics
    tokens_after = sum(len(m.get("content", "")) for m in session.messages) // 4
    if tokens_before > 0:
        reduction = int((1 - tokens_after / tokens_before) * 100)
    else:
        reduction = 0

    console.print()
    table = Table(title="Compact Results", border_style="green", title_justify="left")
    table.add_column("Metric", style="bold")
    table.add_column("Value", style="cyan", justify="right")
    table.add_row("Messages before", str(before_count))
    table.add_row("Messages after", str(after_count))
    table.add_row("Tokens before", f"~{tokens_before:,}")
    table.add_row("Tokens after", f"~{tokens_after:,}")
    table.add_row("Estimated reduction", f"{reduction}%")
    console.print(table)

    console.print("\n[dim]summary.md and memory.md are now injected into future context.[/dim]")


# ── Phase 12 & 13 Commands: Thinking Modes & Status ────────────────────────────


def cmd_think(console: Console, args: list[str]) -> None:
    """Show or set the thinking mode.

    Usage:
        /think              — Show current thinking config
        /think off          — Disable enhanced reasoning
        /think low          — Low reasoning effort
        /think medium       — Medium (default)
        /think high         — High / extended reasoning
    """
    if not args:
        # Show current config
        provider = get_active_provider() or "?"
        model = get_active_model() or "?"
        think = get_thinking_mode()

        table = Table(
            title="Thinking Configuration",
            border_style="magenta",
            title_justify="left",
        )
        table.add_column("Setting", style="bold", no_wrap=True)
        table.add_column("Value", style="cyan")
        table.add_row("Mode", think)
        table.add_row("Provider", provider)
        table.add_row("Model", model)
        console.print(table)
        console.print("\n[dim]Usage: /think off|low|medium|high[/dim]")
        return

    mode = args[0].lower().strip()
    try:
        set_thinking_mode(mode)
        label = mode.upper() if mode != "off" else "OFF"
        console.print(f"[bold green]✓[/bold green] Thinking mode set to [bold]{label}[/bold]")
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")


def cmd_status(console: Console, args: list[str]) -> None:
    """Display current runtime status with all metrics."""
    global _session_mgr

    provider = get_active_provider() or "not set"
    model = get_active_model() or "not set"
    think = get_thinking_mode()
    search_on = is_web_search_enabled()

    table = Table(
        title="Haney Status",
        border_style="cyan",
        title_justify="left",
    )
    table.add_column("Setting", style="bold", no_wrap=True)
    table.add_column("Value", style="cyan")

    table.add_row("Provider", provider)
    table.add_row("Model", model)
    table.add_row("Thinking", think)
    table.add_row("Search", "[green]Enabled[/green]" if search_on else "[yellow]Disabled[/yellow]")
    table.add_row("Mode", "[bold green]EDIT[/bold green]" if get_mode() == "edit" else "[bold cyan]PLAN[/bold cyan]")

    if _session_mgr is not None:
        table.add_section()
        table.add_row("Session Cost", f"${_session_mgr.cost:.4f}")
        table.add_row("Total Tokens", f"{_session_mgr.total_tokens:,}")
        table.add_row("API Calls", str(_session_mgr.api_calls))
        table.add_row("Messages", str(_session_mgr.message_count))

    # Context size from project awareness
    ctx = _get_ctx()
    if ctx.total_tokens:
        table.add_row("Context Size", f"~{ctx.total_tokens:,} tokens")

    console.print(table)


# ── Phase 14 Commands: Plan / Edit Mode ───────────────────────────────────────


def cmd_plan(console: Console, args: list[str]) -> None:
    """Switch to PLAN mode. Blocks tool execution."""
    set_mode("plan")
    console.print("[bold cyan]Mode changed to PLAN.[/bold cyan]")
    console.print("[dim]Tool execution disabled. Use /edit to allow modifications.[/dim]")


def cmd_edit(console: Console, args: list[str]) -> None:
    """Switch to EDIT mode. Enables tool execution."""
    set_mode("edit")
    console.print("[bold green]Mode changed to EDIT.[/bold green]")
    console.print("[dim]File operations enabled. Tool execution enabled.[/dim]")


def cmd_mode_show(console: Console, args: list[str]) -> None:
    """Display the current execution mode."""
    current = get_mode()

    table = Table(title="Current Mode", border_style="cyan", title_justify="left")
    table.add_column("Setting", style="bold", no_wrap=True)
    table.add_column("Value", style="cyan")

    if current == "edit":
        table.add_row("Mode", "[bold green]EDIT[/bold green]")
        table.add_row("Tool Execution", "[green]Enabled[/green]")
    else:
        table.add_row("Mode", "[bold cyan]PLAN[/bold cyan]")
        table.add_row("Tool Execution", "[yellow]Disabled[/yellow]")

    console.print(table)
    console.print("\n[dim]Use /plan or /edit to switch modes.[/dim]")


# ── Permission Commands ───────────────────────────────────────────────────────

_perm_mgr: PermissionManager = PermissionManager()


def set_perm_manager(mgr: PermissionManager) -> None:
    """Set the shared permission manager. Called by chat.py."""
    global _perm_mgr
    _perm_mgr = mgr


def cmd_permission(console: Console, args: list[str]) -> None:
    """Show or set permission mode.

    Usage:
        /permission          — Show current mode
        /permission ask      — Switch to ASK (prompt every time)
        /permission save     — Switch to SAVE (remember for session)
        /permission auto     — Switch to AUTO (auto-approve)
    """
    if not args:
        current = get_permission_mode()
        table = Table(title="Permission Mode", border_style="yellow", title_justify="left")
        table.add_column("Setting", style="bold", no_wrap=True)
        table.add_column("Value", style="cyan")

        label = current.upper()
        if current == "auto":
            label = f"[bold red]{label}[/bold red]"
        elif current == "save":
            label = f"[bold yellow]{label}[/bold yellow]"
        table.add_row("Current", label)

        if current == "save" and _perm_mgr.session_approvals:
            approved = ", ".join(sorted(_perm_mgr.session_approvals))
            table.add_row("Session Approvals", approved)

        console.print(table)
        console.print("\n[dim]Usage: /permission ask | save | auto[/dim]")
        return

    mode = args[0].lower().strip()
    try:
        _perm_mgr.set_mode(mode)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        return

    if mode == "save":
        console.print("[bold yellow]Permission mode: SAVE[/bold yellow]")
        console.print("[yellow]⚠ Approvals are remembered for the current session.[/yellow]")
    elif mode == "auto":
        console.print("[bold red]Permission mode: AUTO[/bold red]")
        console.print("[red]⚠ Haney may modify files without confirmation.[/red]")
    else:
        console.print("[bold green]Permission mode: ASK[/bold green]")
        console.print("[dim]Every modifying action requires confirmation.[/dim]")


# ── MCP Commands ───────────────────────────────────────────────────────────────

_mcp_mgr: MCPServerManager | None = None


def set_mcp_manager(mgr: MCPServerManager) -> None:
    """Set the shared MCP manager. Called by chat.py."""
    global _mcp_mgr
    _mcp_mgr = mgr


def cmd_mcp(console: Console, args: list[str]) -> None:
    """Manage MCP servers and authentication.

    Usage:
        /mcp login <server>     — Authenticate (OAuth or PAT)
        /mcp logout <server>    — Clear stored credentials
        /mcp connect <server>   — Connect to an MCP server
        /mcp disconnect <server> — Disconnect from an MCP server
        /mcp status             — Show connected servers and tools
        /mcp servers            — List available MCP servers
    """
    if not args:
        console.print("[yellow]Usage:[/yellow] /mcp <login|logout|connect|disconnect|status|servers> [server]")
        console.print()
        cmd_mcp_status(console, [])
        return

    sub = args[0].lower().strip()

    if sub == "login":
        cmd_mcp_login(console, args[1:])
    elif sub == "logout":
        cmd_mcp_logout(console, args[1:])
    elif sub == "connect":
        cmd_mcp_connect(console, args[1:])
    elif sub == "disconnect":
        cmd_mcp_disconnect(console, args[1:])
    elif sub in ("status", "list"):
        cmd_mcp_status(console, args[1:])
    elif sub == "servers":
        cmd_mcp_servers(console, args[1:])
    else:
        console.print(f"[red]Unknown MCP sub-command:[/red] {sub}")
        console.print("[dim]Try: /mcp login github, /mcp connect github, /mcp status[/dim]")


def cmd_mcp_servers(console: Console, args: list[str]) -> None:
    """List available MCP server configurations."""
    table = Table(
        title="Available MCP Servers",
        border_style="cyan",
        title_justify="left",
    )
    table.add_column("Server", style="bold cyan", no_wrap=True)
    table.add_column("Description", style="dim")
    table.add_column("Requires", style="yellow")

    for name, cfg in MCP_SERVERS.items():
        requires = []
        if cfg.requires_node:
            requires.append("Node.js / npx")
        if cfg.requires_auth:
            requires.append("Auth token")
        table.add_row(name, cfg.description, ", ".join(requires) if requires else "none")

    console.print(table)

    if _mcp_mgr is not None:
        connected = _mcp_mgr.get_connected_servers()
        if connected:
            console.print(f"\n[dim]Connected: {', '.join(connected)}[/dim]")
        else:
            console.print("\n[dim]No servers connected.[/dim]")

    console.print("\n[dim]Use /mcp login <server> to authenticate first, then /mcp connect <server>.[/dim]")


def cmd_mcp_login(console: Console, args: list[str]) -> None:
    """Authenticate with an MCP server.

    Usage: /mcp login <server>
    Currently supports: github (OAuth device flow or PAT paste)
    """
    if not args:
        console.print("[yellow]Usage:[/yellow] /mcp login <server>")
        console.print()
        cmd_mcp_servers(console, [])
        return

    server_name = args[0].lower().strip()

    if server_name == "github":
        _cmd_mcp_login_github(console)
    else:
        cfg = get_server_config(server_name)
        if cfg is None:
            console.print(f"[red]Unknown MCP server:[/red] {server_name}")
            console.print("[dim]Available servers: github[/dim]")
            return

        console.print(
            f"[yellow]OAuth login not yet available for {cfg.display_name}.[/yellow]"
        )
        console.print(
            f"[dim]To connect, set {cfg.env_token_key} in your environment "
            f"or configure manually in .haney/config.json[/dim]"
        )


def _cmd_mcp_login_github(console: Console) -> None:
    """Handle GitHub authentication for MCP — OAuth device flow or PAT paste."""
    cfg = load_config(Path.cwd())
    github_cfg = cfg.get("mcp", {}).get("servers", {}).get("github", {})

    # Check if already have a token
    existing_token = github_cfg.get("token")
    if existing_token:
        try:
            user_info = GitHubOAuth.check_token(existing_token)
            login_name = user_info.get("login", "unknown")
            console.print(
                f"[yellow]Already authenticated as [bold]{login_name}[/bold] "
                f"on GitHub.[/yellow]"
            )
            if not Confirm.ask("Re-authenticate?", default=False):
                console.print("[dim]Keeping existing GitHub token.[/dim]")
                return
        except GitHubOAuthError:
            console.print("[yellow]Existing token appears invalid. Starting re-auth…[/yellow]")

    # ── Choose auth method ───────────────────────────────────────────
    console.print()
    console.print("[bold]Choose authentication method:[/bold]")
    console.print("  [bold cyan]1.[/bold cyan] GitHub OAuth device flow")
    console.print("  [bold cyan]2.[/bold cyan] Paste a Personal Access Token (classic or fine-grained)")
    console.print()

    choice = Prompt.ask(
        "Enter choice",
        choices=["1", "2"],
        default="1",
    )

    if choice == "1":
        token = _mcp_github_oauth_flow(console)
        if token is None:
            return
    else:
        token = _mcp_github_pat_flow(console)
        if token is None:
            return

    # Verify the token
    console.print()
    console.print("[dim]Verifying token…[/dim]")
    try:
        user_info = GitHubOAuth.check_token(token)
        login_name = user_info.get("login", "unknown")
    except GitHubOAuthError as exc:
        console.print(f"[red]Token verification failed:[/red] {exc}")
        return

    # Store in config
    if "mcp" not in cfg:
        cfg["mcp"] = {}
    if "servers" not in cfg["mcp"]:
        cfg["mcp"]["servers"] = {}
    if "github" not in cfg["mcp"]["servers"]:
        cfg["mcp"]["servers"]["github"] = {}

    cfg["mcp"]["servers"]["github"]["token"] = token
    cfg["mcp"]["servers"]["github"]["enabled"] = True
    cfg["mcp"]["enabled"] = True
    save_config(cfg, Path.cwd())

    console.print()
    console.print(
        f"[bold green]✓[/bold green] Authenticated as [bold]{login_name}[/bold] on GitHub"
    )
    console.print("[dim]Token stored in .haney/config.json[/dim]")
    console.print()
    console.print("[dim]Next: use [bold]/mcp connect github[/bold] to start the GitHub MCP server.[/dim]")


def _mcp_github_oauth_flow(console: Console) -> str | None:
    """Run the GitHub OAuth device flow.

    Returns:
        Access token string, or None if cancelled/failed.
    """
    try:
        oauth = GitHubOAuth(console=console)
        token = oauth.login()
    except GitHubOAuthError as exc:
        console.print(f"[red]GitHub OAuth failed:[/red] {exc}")
        return None
    return token


def _mcp_github_pat_flow(console: Console) -> str | None:
    """Prompt the user to paste a GitHub Personal Access Token.

    Returns:
        Validated token string, or None if cancelled.
    """
    console.print()
    console.print("[bold]GitHub Personal Access Token[/bold]")
    console.print(
        "[dim]Generate one at: "
        "[underline]https://github.com/settings/tokens[/underline][/dim]"
    )
    console.print()
    console.print("[dim]Classic tokens need: [bold]repo[/bold], [bold]read:user[/bold] scopes[/dim]")
    console.print("[dim]Fine-grained tokens: read/write access to repositories and user[/dim]")
    console.print()

    token = Prompt.ask(
        "Paste your GitHub PAT (hidden input)",
        password=True,
    )

    if not token or not token.strip():
        console.print("[red]No token provided. Login cancelled.[/red]")
        return None

    token = token.strip()

    # Quick format check
    if not token.startswith(("ghp_", "github_pat_", "gho_")):
        console.print()
        console.print(
            "[yellow]⚠ Token doesn't match expected GitHub PAT format "
            "(ghp_..., github_pat_..., gho_...).[/yellow]"
        )
        if not Confirm.ask("Use this token anyway?", default=False):
            console.print("[dim]Login cancelled.[/dim]")
            return None

    return token


def cmd_mcp_logout(console: Console, args: list[str]) -> None:
    """Clear stored credentials for an MCP server.

    Usage: /mcp logout <server>
    """
    if not args:
        console.print("[yellow]Usage:[/yellow] /mcp logout <server>")
        return

    server_name = args[0].lower().strip()

    # Disconnect first if connected
    if _mcp_mgr is not None and _mcp_mgr.is_connected(server_name):
        _mcp_mgr.disconnect(server_name)
        console.print(f"[dim]Disconnected from {server_name} MCP server.[/dim]")

    # Clear from config
    cfg = load_config(Path.cwd())
    servers = cfg.get("mcp", {}).get("servers", {})
    if server_name in servers:
        srv = servers[server_name]
        srv.pop("token", None)
        srv["enabled"] = False
        cfg["mcp"]["servers"][server_name] = srv
        save_config(cfg, Path.cwd())

    console.print(f"[bold green]✓[/bold green] Cleared credentials for [bold]{server_name}[/bold]")
    console.print("[dim]Run /mcp login <server> to re-authenticate.[/dim]")


def cmd_mcp_connect(console: Console, args: list[str]) -> None:
    """Connect to an MCP server.

    Usage: /mcp connect <server>
    Requires prior authentication via /mcp login <server>.
    """
    if _mcp_mgr is None:
        console.print("[red]MCP manager not available. Restart Haney.[/red]")
        return

    if not args:
        console.print("[yellow]Usage:[/yellow] /mcp connect <server>")
        console.print("[dim]Available: github[/dim]")
        return

    server_name = args[0].lower().strip()

    if _mcp_mgr.is_connected(server_name):
        tools = _mcp_mgr.get_tool_count()
        console.print(
            f"[yellow]{server_name} is already connected with {tools} tool(s).[/yellow]"
        )
        return

    cfg = load_config(Path.cwd())
    server_cfg_raw = cfg.get("mcp", {}).get("servers", {}).get(server_name, {})
    srv_config = get_server_config(server_name)

    if srv_config is None and not server_cfg_raw:
        console.print(f"[red]Unknown MCP server:[/red] {server_name}")
        return

    # Merge predefined config with user config
    run_cfg: dict = {
        "command": server_cfg_raw.get("command", srv_config.command if srv_config else ""),
        "args": server_cfg_raw.get("args", srv_config.args if srv_config else []),
        "env": dict(server_cfg_raw.get("env", {})),
        "token": server_cfg_raw.get("token"),
        "env_token_key": server_cfg_raw.get(
            "env_token_key",
            srv_config.env_token_key if srv_config else "",
        ),
    }

    token = run_cfg.get("token")
    token_key = run_cfg.get("env_token_key", "")

    if not token and srv_config and srv_config.requires_auth:
        # Check environment variable
        import os
        env_token = os.environ.get(token_key) if token_key else None
        if env_token:
            run_cfg["token"] = env_token
        else:
            console.print(
                f"[red]No token configured for {server_name}.[/red]"
            )
            console.print(
                f"[dim]Run /mcp login {server_name} to authenticate, or "
                f"set {token_key} in your environment.[/dim]"
            )
            return

    if srv_config and srv_config.requires_node:
        # Check if npx / node is available
        import shutil
        npx_path = shutil.which("npx")
        if npx_path is None:
            console.print(
                "[red]npx is required but not found. Install Node.js: "
                "https://nodejs.org/[/red]"
            )
            return
        console.print(f"[dim]Found npx: {npx_path}[/dim]")

    try:
        server = _mcp_mgr.connect(server_name, run_cfg)
    except Exception as exc:
        console.print(f"[red]Failed to connect to {server_name}: {exc}[/red]")
        return

    # Update config to remember this server is enabled
    if "mcp" not in cfg:
        cfg["mcp"] = {"enabled": True, "servers": {}}
    if "servers" not in cfg["mcp"]:
        cfg["mcp"]["servers"] = {}
    if server_name not in cfg["mcp"]["servers"]:
        cfg["mcp"]["servers"][server_name] = {}
    cfg["mcp"]["enabled"] = True
    cfg["mcp"]["servers"][server_name]["enabled"] = True
    save_config(cfg, Path.cwd())

    tools_count = len(server.tool_defs)
    console.print(
        f"[bold green]✓[/bold green] Connected to {server_name} MCP — "
        f"{tools_count} tool(s) available."
    )


def cmd_mcp_disconnect(console: Console, args: list[str]) -> None:
    """Disconnect from an MCP server.

    Usage: /mcp disconnect <server>
    """
    if _mcp_mgr is None:
        console.print("[red]MCP manager not available.[/red]")
        return

    if not args:
        # Disconnect all
        connected = _mcp_mgr.get_connected_servers()
        if not connected:
            console.print("[yellow]No MCP servers are connected.[/yellow]")
            return
        for name in list(connected):
            _mcp_mgr.disconnect(name)
            console.print(f"[dim]Disconnected from {name}.[/dim]")
        console.print("[bold green]✓[/bold green] All MCP servers disconnected.")
        return

    server_name = args[0].lower().strip()

    if not _mcp_mgr.is_connected(server_name):
        console.print(f"[yellow]{server_name} is not connected.[/yellow]")
        return

    _mcp_mgr.disconnect(server_name)
    console.print(f"[bold green]✓[/bold green] Disconnected from [bold]{server_name}[/bold] MCP.")

    # Update config
    cfg = load_config(Path.cwd())
    servers = cfg.get("mcp", {}).get("servers", {})
    if server_name in servers:
        servers[server_name]["enabled"] = False
        save_config(cfg, Path.cwd())


def cmd_mcp_status(console: Console, args: list[str]) -> None:
    """Show MCP connection status and available tools.

    Usage: /mcp status
    """
    if _mcp_mgr is None:
        console.print("[yellow]MCP manager not initialised.[/yellow]")
        return

    cfg = load_config(Path.cwd())
    mcp_cfg = cfg.get("mcp", {})
    mcp_enabled = mcp_cfg.get("enabled", False)

    table = Table(
        title="MCP Status",
        border_style="magenta",
        title_justify="left",
    )
    table.add_column("Setting", style="bold", no_wrap=True)
    table.add_column("Value", style="cyan")

    table.add_row(
        "Global",
        "[green]Enabled[/green]" if mcp_enabled else "[yellow]Disabled[/yellow]",
    )

    connected = _mcp_mgr.get_connected_servers()
    table.add_row("Connected Servers", ", ".join(connected) if connected else "[dim]none[/dim]")
    table.add_row("Total MCP Tools", str(_mcp_mgr.get_tool_count()))

    console.print(table)

    # Show per-server details
    servers_cfg = mcp_cfg.get("servers", {})
    if servers_cfg:
        console.print()
        detail_table = Table(
            title="MCP Servers",
            border_style="cyan",
            title_justify="left",
        )
        detail_table.add_column("Server", style="bold cyan")
        detail_table.add_column("Auth", style="dim")
        detail_table.add_column("Connected", style="bold")
        detail_table.add_column("Tools", style="cyan", justify="right")

        for name, srv_cfg in servers_cfg.items():
            if not isinstance(srv_cfg, dict):
                continue
            has_token = bool(srv_cfg.get("token"))
            is_conn = name in connected
            tool_count = 0

            # Count tools if connected
            if is_conn and _mcp_mgr._servers.get(name):
                tool_count = len(_mcp_mgr._servers[name].tool_defs)

            detail_table.add_row(
                name,
                "[green]✓[/green]" if has_token else "[yellow]✗[/yellow]",
                "[green]Yes[/green]" if is_conn else "[dim]No[/dim]",
                str(tool_count) if is_conn else "—",
            )

        console.print(detail_table)

    # Show available but not configured
    configured = set(servers_cfg.keys()) if servers_cfg else set()
    unconfigured = set(MCP_SERVERS.keys()) - configured
    if unconfigured:
        console.print(
            f"\n[dim]Not configured: {', '.join(sorted(unconfigured))}. "
            "Use /mcp login <server> to set up.[/dim]"
        )


# ── Command Registry ───────────────────────────────────────────────────────────

def get_commands() -> dict[str, Command]:
    """Return a mapping of command names to Command objects.

    Returns:
        Dictionary mapping slash-command names (with prefix) to Command instances.
    """
    return {
        # Phase 1
        "/help": Command(name="/help", description="Display help", handler=cmd_help),
        "/version": Command(name="/version", description="Show version", handler=cmd_version),
        "/clear": Command(name="/clear", description="Clear screen", handler=cmd_clear),
        "/exit": Command(name="/exit", description="Exit Haney", handler=cmd_exit),
        # Phase 2
        "/login": Command(name="/login", description="Connect a provider", handler=cmd_login),
        "/logout": Command(name="/logout", description="Disconnect provider", handler=cmd_logout),
        "/models": Command(name="/models", description="List models", handler=cmd_models),
        "/model": Command(name="/model", description="Show/set model", handler=cmd_model),
        "/provider": Command(name="/provider", description="Show provider status", handler=cmd_provider),
        # Phase 5
        "/project": Command(name="/project", description="Project status", handler=cmd_project),
        "/reload": Command(name="/reload", description="Re-scan project", handler=cmd_reload),
        "/context": Command(name="/context", description="Context details", handler=cmd_context),
        "/init": Command(name="/init", description="Generate project files", handler=cmd_init),
        # Phase 7
        "/trash": Command(name="/trash", description="Show trash contents", handler=cmd_trash),
        "/restore": Command(name="/restore", description="Restore file from trash", handler=cmd_restore),
        # Phase 8
        "/history": Command(name="/history", description="Show recent sessions", handler=cmd_history),
        "/session": Command(name="/session", description="Current session info", handler=cmd_session),
        "/stats": Command(name="/stats", description="Token & cost metrics", handler=cmd_stats),
        # Phase 10 & 11
        "/remember": Command(name="/remember", description="Save to memory.md", handler=cmd_remember),
        "/summary": Command(name="/summary", description="Show project summary", handler=cmd_summary),
        "/compact": Command(name="/compact", description="Compact conversation", handler=cmd_remember),  # stub — real handler in dispatch
        # Phase 12 & 13
        "/think": Command(name="/think", description="Show/set thinking mode", handler=cmd_think),
        "/status": Command(name="/status", description="Runtime status", handler=cmd_status),
        # Phase 14
        "/plan": Command(name="/plan", description="Switch to PLAN mode", handler=cmd_plan),
        "/edit": Command(name="/edit", description="Switch to EDIT mode", handler=cmd_edit),
        "/mode": Command(name="/mode", description="Show current mode", handler=cmd_mode_show),
        # Permission
        "/permission": Command(name="/permission", description="Show/set permission mode", handler=cmd_permission),
        # MCP
        "/mcp": Command(name="/mcp", description="Manage MCP servers", handler=cmd_mcp),
    }


def dispatch(user_input: str, console: Console, session: "ChatSession | None" = None) -> None:
    """Parse user input and dispatch to the appropriate handler.

    If the input starts with the command prefix, it is routed to the
    command handler. Otherwise, it is treated as a chat message and
    sent to the LLM via the ChatSession.

    Args:
        user_input: The raw user input string.
        console: Rich Console instance for output.
        session: Active ChatSession for LLM calls. Created if not provided.
    """
    stripped = user_input.strip()

    if not stripped.startswith(COMMAND_PREFIX):
        # Chat message — send to LLM
        if session is None:
            from haney.llm import ChatSession
            session = ChatSession(console)

        try:
            session.send(stripped)
        except RuntimeError as exc:
            console.print(f"[red]Error:[/red] {exc}")
        except Exception as exc:
            console.print(f"[red]Unexpected error:[/red] {exc}")
        return

    commands = get_commands()
    # Extract the command name (first word after /) and remaining args
    parts = stripped.split(maxsplit=1)
    cmd_name = parts[0].lower()
    cmd_args = parts[1].split() if len(parts) > 1 else []

    # /clear also clears conversation and attachments
    if cmd_name == "/clear" and session is not None:
        session.clear()

    # /attachments shows file context via session
    if cmd_name == "/attachments":
        if session is not None:
            session.file_ctx.display_summary(console)
        else:
            console.print("[dim]No active session. Attach files with @filename in a chat message.[/dim]")
        return

    # /compact needs the session for LLM call and message truncation
    if cmd_name == "/compact":
        if session is not None:
            cmd_compact(console, session)
        else:
            console.print("[yellow]No active session. Start a conversation first.[/yellow]")
        return

    if cmd_name in commands:
        commands[cmd_name].handler(console, cmd_args)
    else:
        console.print(f"[red]Unknown command:[/red] {cmd_name}")
        console.print("[dim]Type /help to see available commands.[/dim]")
