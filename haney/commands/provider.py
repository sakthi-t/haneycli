"""Provider management commands: /login, /logout, /models, /model, /provider."""

from __future__ import annotations

import os

from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table

from haney.providers import (
    PROVIDERS,
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
from haney.thinking_manager import get_thinking_mode
from haney.providers import load_config, save_config


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

    table.add_row(
        "[bold]Exa Search[/bold]",
        "/login exa",
        "[dim]Web search enrichment[/dim]",
    )

    console.print(table)


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

    if provider_name == "exa":
        _cmd_login_exa(console)
        return

    if provider_name not in PROVIDERS:
        console.print(f"[red]Unknown provider:[/red] {provider_name}")
        console.print()
        _list_providers(console)
        return

    info = PROVIDERS[provider_name]

    existing_key = get_api_key(provider_name)
    if existing_key:
        console.print(
            f"[yellow]Already logged into {info.display_name} "
            f"(key: {mask_api_key(existing_key)})[/yellow]"
        )
        if not Confirm.ask("Re-enter API key?", default=False):
            console.print("[dim]Login cancelled. Keeping existing credentials.[/dim]")
            return

    env_key = os.environ.get(info.env_key)
    if env_key and not existing_key:
        masked = mask_api_key(env_key)
        console.print(f"[dim]Found {info.env_key} in environment ({masked})[/dim]")
        use_env = Confirm.ask(
            f"Use this environment key for {info.display_name}?", default=True
        )
        if use_env:
            login_provider(provider_name, env_key)
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

    if provider_name == "exa":
        if not is_search_logged_in():
            console.print("[yellow]Not logged into Exa.[/yellow]")
            return
        logout_search()
        console.print("[bold green]✓[/bold green] Logged out from [bold]Exa Search[/bold]")
        console.print("[dim]API key removed from .haney/config.json[/dim]")
        return

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
