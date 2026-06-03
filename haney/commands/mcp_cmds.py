"""MCP commands: /mcp login|logout|connect|disconnect|status|servers."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table

from haney.providers import load_config, save_config
from haney.mcp.server_configs import get_server_config, MCP_SERVERS
from haney.mcp.github_oauth import GitHubOAuth, GitHubOAuthError
from haney.commands._state import get_mcp_manager


# ── Public handler: /mcp ──────────────────────────────────────────────────────

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


# ── /mcp servers ─────────────────────────────────────────────────────────────

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

    mcp_mgr = get_mcp_manager()
    if mcp_mgr is not None:
        connected = mcp_mgr.get_connected_servers()
        if connected:
            console.print(f"\n[dim]Connected: {', '.join(connected)}[/dim]")
        else:
            console.print("\n[dim]No servers connected.[/dim]")

    console.print("\n[dim]Use /mcp login <server> to authenticate first, then /mcp connect <server>.[/dim]")


# ── /mcp login ───────────────────────────────────────────────────────────────

def cmd_mcp_login(console: Console, args: list[str]) -> None:
    """Authenticate with an MCP server.

    Usage: /mcp login <server>
    """
    if not args:
        console.print("[yellow]Usage:[/yellow] /mcp login <server>")
        console.print()
        cmd_mcp_servers(console, [])
        return

    server_name = args[0].lower().strip()

    if server_name == "github":
        _cmd_mcp_login_github(console)
    elif server_name == "stackoverflow":
        _cmd_mcp_login_stackoverflow(console)
    elif server_name == "duckduckgo":
        _cmd_mcp_login_duckduckgo(console)
    elif server_name == "mdn":
        _cmd_mcp_login_mdn(console)
    elif server_name == "filesystem":
        _cmd_mcp_login_filesystem(console)
    elif server_name == "langchain":
        _cmd_mcp_login_langchain(console)
    elif server_name == "playwright":
        _cmd_mcp_login_playwright(console)
    else:
        cfg = get_server_config(server_name)
        if cfg is None:
            console.print(f"[red]Unknown MCP server:[/red] {server_name}")
            available = ", ".join(sorted(MCP_SERVERS.keys()))
            console.print(f"[dim]Available servers: {available}[/dim]")
            return

        console.print(
            f"[yellow]OAuth login not yet available for {cfg.display_name}.[/yellow]"
        )
        console.print(
            f"[dim]To connect, set {cfg.env_token_key} in your environment "
            f"or configure manually in .haney/config.json[/dim]"
        )


# ── Server-specific login handlers ──────────────────────────────────────────

def _cmd_mcp_login_github(console: Console) -> None:
    """Handle GitHub authentication — OAuth device flow or PAT paste."""
    cfg = load_config(Path.cwd())
    github_cfg = cfg.get("mcp", {}).get("servers", {}).get("github", {})

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

    console.print()
    console.print("[dim]Verifying token…[/dim]")
    try:
        user_info = GitHubOAuth.check_token(token)
        login_name = user_info.get("login", "unknown")
    except GitHubOAuthError as exc:
        console.print(f"[red]Token verification failed:[/red] {exc}")
        return

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


def _cmd_mcp_login_stackoverflow(console: Console) -> None:
    """Handle Stack Overflow MCP authentication — browser-based OAuth."""
    cfg = load_config(Path.cwd())

    console.print()
    console.print("[bold]Stack Overflow MCP Authentication[/bold]")
    console.print()
    console.print(
        "Stack Overflow MCP uses [bold cyan]browser-based OAuth[/bold cyan] "
        "via [dim]mcp-remote[/dim]."
    )
    console.print()
    console.print("  [bold]1.[/bold] When you connect, [dim]mcp-remote[/dim] will open your browser automatically.")
    console.print("  [bold]2.[/bold] Log in with your Stack Overflow account.")
    console.print("  [bold]3.[/bold] Authorize the MCP client — no token to paste.")
    console.print()
    console.print("[dim]Note: Limited to 100 calls/day per user during beta.[/dim]")
    console.print()

    if "mcp" not in cfg:
        cfg["mcp"] = {}
    if "servers" not in cfg["mcp"]:
        cfg["mcp"]["servers"] = {}
    if "stackoverflow" not in cfg["mcp"]["servers"]:
        cfg["mcp"]["servers"]["stackoverflow"] = {}
    cfg["mcp"]["servers"]["stackoverflow"]["enabled"] = True
    cfg["mcp"]["enabled"] = True
    save_config(cfg, Path.cwd())

    console.print("[bold green]✓[/bold green] Stack Overflow MCP enabled.")
    console.print()
    console.print("[dim]Next: use [bold]/mcp connect stackoverflow[/bold] to start the Stack Overflow MCP server.[/dim]")
    console.print("[dim]Your browser will open for Stack Overflow authentication.[/dim]")


def _cmd_mcp_login_duckduckgo(console: Console) -> None:
    """Handle DuckDuckGo MCP setup — no authentication needed."""
    cfg = load_config(Path.cwd())

    console.print()
    console.print("[bold]DuckDuckGo MCP — No Authentication Required[/bold]")
    console.print()
    console.print("DuckDuckGo MCP provides web search and content fetching without any API key.")
    console.print()
    console.print("  [bold cyan]search[/bold cyan] — Search DuckDuckGo with rate limiting and LLM-friendly Markdown results")
    console.print("  [bold cyan]fetch_content[/bold cyan] — Retrieve and parse webpage content with intelligent text extraction")
    console.print()
    console.print("[dim]Powered by:[/dim] [underline]https://pypi.org/project/duckduckgo-mcp-server/[/underline]")
    console.print("[dim]Run via: uvx duckduckgo-mcp-server[/dim]")
    console.print()

    if "mcp" not in cfg:
        cfg["mcp"] = {}
    if "servers" not in cfg["mcp"]:
        cfg["mcp"]["servers"] = {}
    if "duckduckgo" not in cfg["mcp"]["servers"]:
        cfg["mcp"]["servers"]["duckduckgo"] = {}
    cfg["mcp"]["servers"]["duckduckgo"]["enabled"] = True
    cfg["mcp"]["enabled"] = True
    save_config(cfg, Path.cwd())

    console.print("[bold green]✓[/bold green] DuckDuckGo MCP enabled (no auth required).")
    console.print()
    console.print("[dim]Next: use [bold]/mcp connect duckduckgo[/bold] to start the DuckDuckGo MCP server.[/dim]")


def _cmd_mcp_login_mdn(console: Console) -> None:
    """Handle MDN MCP setup — no authentication needed."""
    cfg = load_config(Path.cwd())

    console.print()
    console.print("[bold]MDN Web Docs MCP — No Authentication Required[/bold]")
    console.print()
    console.print("MDN Web Docs MCP provides access to Mozilla's web documentation directly from your AI assistant.")
    console.print()
    console.print("  [bold cyan]Tools available:[/bold cyan]")
    console.print("    • mdn_search  — Search MDN by keyword")
    console.print("    • mdn_doc     — Fetch full documentation for a page")
    console.print("    • mdn_compat  — Browser compatibility check")
    console.print("    • mdn_list    — Browse BCD features by namespace")
    console.print("    • mdn_css     — CSS property formal definitions")
    console.print("    • mdn_http    — HTTP headers, status codes, methods reference")
    console.print()
    console.print(
        "[bold yellow]⚠️  Privacy Notice:[/bold yellow] "
        "This MCP server is experimental. MDN stores query data "
        "for analysis. Data is [bold]not[/bold] associated with "
        "identifiable user information. However, private info "
        "shared with the LLM could appear in queries."
    )
    console.print()
    console.print(
        "[bold green]✓ Opt-out enabled by default:[/bold green] "
        "The [cyan]MOZ_OPT_OUT=1[/cyan] env var is set, sending "
        "[cyan]X-Moz-1st-Party-Data-Opt-Out: 1[/cyan] header "
        "with all requests to disable first-party analytics."
    )
    console.print("[dim]To allow analytics, set MOZ_OPT_OUT=0 in .haney/config.json → mcp.servers.mdn.env[/dim]")
    console.print()
    console.print(
        "[bold yellow]📜 Acceptable Use Policy:[/bold yellow] "
        "By using the MDN MCP server, you agree to comply with "
        "[underline]https://www.mozilla.org/about/legal/acceptable-use/[/underline]"
    )
    console.print()
    console.print("[bold yellow]⚠️  Experimental:[/bold yellow] This MCP server is experimental and may be withdrawn at any time.")
    console.print()
    console.print(
        "[bold cyan]💬 Feedback & Contribution:[/bold cyan] "
        "We welcome any feedback! Chat with us on "
        "[underline]https://discord.gg/mdn[/underline] "
        "or open an issue at "
        "[underline]https://github.com/mdn/mcp[/underline]"
    )
    console.print()
    console.print("[dim]Powered by:[/dim] [underline]https://github.com/mdn/mcp[/underline]")
    console.print("[dim]Run via: npx -y mdn-mcp[/dim]")
    console.print()

    if "mcp" not in cfg:
        cfg["mcp"] = {}
    if "servers" not in cfg["mcp"]:
        cfg["mcp"]["servers"] = {}
    if "mdn" not in cfg["mcp"]["servers"]:
        cfg["mcp"]["servers"]["mdn"] = {}
    cfg["mcp"]["servers"]["mdn"]["enabled"] = True
    cfg["mcp"]["enabled"] = True
    save_config(cfg, Path.cwd())

    console.print("[bold green]✓[/bold green] MDN Web Docs MCP enabled (no auth required).")
    console.print()
    console.print("[dim]Next: use [bold]/mcp connect mdn[/bold] to start the MDN MCP server.[/dim]")


def _cmd_mcp_login_filesystem(console: Console) -> None:
    """Handle Filesystem MCP setup — no authentication needed."""
    cfg = load_config(Path.cwd())

    console.print()
    console.print("[bold]Filesystem MCP — No Authentication Required[/bold]")
    console.print()
    console.print("Filesystem MCP provides secure, OS-level file operations scoped to directories you specify.")
    console.print()
    console.print("  [bold cyan]Tools available:[/bold cyan]")
    console.print("    • read_file       — Read a complete file")
    console.print("    • write_file      — Create or overwrite a file")
    console.print("    • edit_file       — Make line-based edits")
    console.print("    • create_directory — Create directories")
    console.print("    • list_directory  — List directory contents")
    console.print("    • directory_tree  — Recursive tree view")
    console.print("    • move_file       — Move or rename files/directories")
    console.print("    • search_files    — Search for files matching a pattern")
    console.print("    • get_file_info   — Retrieve file metadata")
    console.print("    • list_allowed_directories — Show accessible paths")
    console.print()
    console.print(
        "[bold yellow]🔒 Scoped Access:[/bold yellow] "
        "The server only accesses directories passed as arguments. "
        "By default this is the current project root. Configure "
        "additional directories via the [cyan]args[/cyan] field in "
        "[dim].haney/config.json → mcp.servers.filesystem.args[/dim]"
    )
    console.print()
    console.print(
        "[bold yellow]⚠️  Note:[/bold yellow] This is an additional "
        "filesystem layer on top of Haney's built-in tool system. "
        "It can access [bold]any[/bold] configured directory — not "
        "just the project root. Use with appropriate scoping."
    )
    console.print()
    console.print("[dim]Powered by:[/dim] [underline]https://github.com/modelcontextprotocol/servers[/underline]")
    console.print("[dim]Run via: npx -y @modelcontextprotocol/server-filesystem <dirs...>[/dim]")
    console.print()

    default_args = ["."]

    if "mcp" not in cfg:
        cfg["mcp"] = {}
    if "servers" not in cfg["mcp"]:
        cfg["mcp"]["servers"] = {}
    if "filesystem" not in cfg["mcp"]["servers"]:
        cfg["mcp"]["servers"]["filesystem"] = {}

    fs_cfg = cfg["mcp"]["servers"]["filesystem"]
    if "args" not in fs_cfg or not fs_cfg["args"]:
        fs_cfg["args"] = default_args
    fs_cfg["enabled"] = True
    fs_cfg["command"] = "npx"
    if "env" not in fs_cfg:
        fs_cfg["env"] = {}
    if "env_token_key" not in fs_cfg:
        fs_cfg["env_token_key"] = ""

    cfg["mcp"]["enabled"] = True
    save_config(cfg, Path.cwd())

    console.print("[bold green]✓[/bold green] Filesystem MCP enabled (no auth required).")
    console.print(f"[dim]Allowed directories: {fs_cfg['args']}[/dim]")
    console.print()
    console.print("[dim]To add more directories, edit [cyan].haney/config.json[/cyan] → mcp.servers.filesystem.args[/dim]")
    console.print()
    console.print("[dim]Next: use [bold]/mcp connect filesystem[/bold] to start the Filesystem MCP server.[/dim]")


def _cmd_mcp_login_langchain(console: Console) -> None:
    """Handle LangChain MCP authentication — Google OAuth via browser."""
    cfg = load_config(Path.cwd())

    console.print()
    console.print("[bold]LangChain MCP — Google OAuth Authentication[/bold]")
    console.print()
    console.print(
        "LangChain MCP provides access to LangChain, LangGraph, and DeepAgents "
        "documentation, code search, and LangGraph agent debugging tools."
    )
    console.print()
    console.print("  [bold cyan]Tools available:[/bold cyan]")
    console.print("    • search_docs           — Search LangChain/LangGraph/DeepAgents docs")
    console.print("    • search_langchain_code — Search LangChain source code (Python/JS)")
    console.print("    • search_langgraph_code — Search LangGraph source code (Python/JS)")
    console.print("    • search_deepagents_code — Search DeepAgents source code")
    console.print("    • langgraph_list_threads — List LangGraph dev server threads")
    console.print("    • langgraph_get_thread  — Get thread details from dev server")
    console.print("    • langgraph_get_thread_state — Get thread state/checkpoint")
    console.print("    • langgraph_list_runs   — List runs for a thread")
    console.print("    • langgraph_get_run     — Get run trace details")
    console.print()
    console.print(
        "[bold cyan]Authentication:[/bold cyan] Google OAuth via browser. "
        "Credentials are stored by the langchain-mcp package locally."
    )
    console.print()
    console.print("[dim]Powered by:[/dim] [underline]https://github.com/langchain-ai/langchain-mcp[/underline]")
    console.print("[dim]Run via: npx -y langchain-mcp[/dim]")
    console.print()

    npx_path = shutil.which("npx")
    if npx_path is None:
        console.print("[red]npx is required but not found. Install Node.js: https://nodejs.org/[/red]")
        return

    if "mcp" not in cfg:
        cfg["mcp"] = {}
    if "servers" not in cfg["mcp"]:
        cfg["mcp"]["servers"] = {}
    if "langchain" not in cfg["mcp"]["servers"]:
        cfg["mcp"]["servers"]["langchain"] = {}
    cfg["mcp"]["servers"]["langchain"]["enabled"] = True
    cfg["mcp"]["enabled"] = True
    save_config(cfg, Path.cwd())

    console.print("[bold green]✓[/bold green] LangChain MCP enabled.")
    console.print()
    console.print("[bold]Starting Google OAuth login…[/bold] A browser window will open for you to sign in with Google.")
    console.print()
    console.print("[dim]Running: npx -y langchain-mcp login[/dim]")

    try:
        result = subprocess.run(
            ["npx", "-y", "langchain-mcp", "login"],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            console.print()
            console.print("[bold green]✓[/bold green] LangChain MCP authentication complete!")
            if result.stdout.strip():
                console.print(f"[dim]{result.stdout.strip()}[/dim]")
        else:
            console.print()
            console.print(f"[yellow]⚠ Login process exited with code {result.returncode}.[/yellow]")
            if result.stderr.strip():
                console.print(f"[dim]{result.stderr.strip()}[/dim]")
            console.print()
            console.print("[dim]You can also run it manually in another terminal:[/dim]")
            console.print("[cyan]  npx -y langchain-mcp login[/cyan]")
            console.print("[dim]Then run [bold]/mcp connect langchain[/bold] here.[/dim]")
    except subprocess.TimeoutExpired:
        console.print()
        console.print("[yellow]⚠ Login timed out (2 minute limit).[/yellow]")
        console.print()
        console.print("[dim]You can run it manually:[/dim]")
        console.print("[cyan]  npx -y langchain-mcp login[/cyan]")
    except FileNotFoundError:
        console.print("[red]npx not found. Please install Node.js.[/red]")
        return

    console.print()
    console.print("[dim]Next: use [bold]/mcp connect langchain[/bold] to start the LangChain MCP server.[/dim]")


def _cmd_mcp_login_playwright(console: Console) -> None:
    """Handle Playwright MCP — no auth required, just browser setup info."""
    console.print()
    console.print("[bold]Playwright MCP — Browser Automation[/bold]")
    console.print()
    console.print("[bold cyan]No authentication required![/bold cyan]")
    console.print()
    console.print(
        "Playwright MCP provides browser automation tools: navigate web pages, "
        "take screenshots, click elements, fill forms, intercept network requests, "
        "and extract page content."
    )
    console.print()
    console.print("  [bold cyan]Tools include:[/bold cyan]")
    console.print("    • browser_navigate     — Navigate to a URL")
    console.print("    • browser_screenshot   — Take a screenshot")
    console.print("    • browser_click        — Click an element")
    console.print("    • browser_type         — Type into an input")
    console.print("    • browser_fill_form    — Fill multiple form fields")
    console.print("    • browser_snapshot     — Get accessibility snapshot")
    console.print("    • browser_evaluate     — Run JavaScript in page")
    console.print("    • browser_network_requests — View network activity")
    console.print("    • browser_console_messages — View console messages")
    console.print()

    npx_path = shutil.which("npx")
    if npx_path is None:
        console.print("[red]npx is required but not found. Install Node.js: https://nodejs.org/[/red]")
        return

    console.print(f"[dim]Found npx: {npx_path}[/dim]")

    playwright_browsers = (Path.home() / ".cache" / "ms-playwright").exists()
    if not playwright_browsers:
        console.print()
        console.print("[yellow]⚠ Playwright browser binaries may not be installed.[/yellow]")
        console.print("[dim]Run this once to install Chromium, Firefox, and WebKit:[/dim]")
        console.print("[cyan]  npx playwright install[/cyan]")
        console.print("[dim]Or for just Chromium (smaller download):[/dim]")
        console.print("[cyan]  npx playwright install chromium[/cyan]")
    else:
        console.print("[dim]✓ Playwright browser cache found.[/dim]")

    console.print()
    console.print("[bold green]✓[/bold green] No login needed — run [bold]/mcp connect playwright[/bold] to start.")


# ── OAuth helpers ─────────────────────────────────────────────────────────────

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
    console.print("[dim]Generate one at: [underline]https://github.com/settings/tokens[/underline][/dim]")
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


# ── /mcp logout ──────────────────────────────────────────────────────────────

def cmd_mcp_logout(console: Console, args: list[str]) -> None:
    """Clear stored credentials for an MCP server.

    Usage: /mcp logout <server>
    """
    if not args:
        console.print("[yellow]Usage:[/yellow] /mcp logout <server>")
        return

    server_name = args[0].lower().strip()
    mcp_mgr = get_mcp_manager()

    if mcp_mgr is not None and mcp_mgr.is_connected(server_name):
        mcp_mgr.disconnect(server_name)
        console.print(f"[dim]Disconnected from {server_name} MCP server.[/dim]")

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


# ── /mcp connect ─────────────────────────────────────────────────────────────

def cmd_mcp_connect(console: Console, args: list[str]) -> None:
    """Connect to an MCP server.

    Usage: /mcp connect <server>
    """
    mcp_mgr = get_mcp_manager()
    if mcp_mgr is None:
        console.print("[red]MCP manager not available. Restart Haney.[/red]")
        return

    if not args:
        console.print("[yellow]Usage:[/yellow] /mcp connect <server>")
        available = ", ".join(sorted(MCP_SERVERS.keys()))
        console.print(f"[dim]Available: {available}[/dim]")
        return

    server_name = args[0].lower().strip()

    if mcp_mgr.is_connected(server_name):
        tools = mcp_mgr.get_tool_count()
        console.print(f"[yellow]{server_name} is already connected with {tools} tool(s).[/yellow]")
        return

    cfg = load_config(Path.cwd())
    server_cfg_raw = cfg.get("mcp", {}).get("servers", {}).get(server_name, {})
    srv_config = get_server_config(server_name)

    if srv_config is None and not server_cfg_raw:
        console.print(f"[red]Unknown MCP server:[/red] {server_name}")
        return

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
        env_token = os.environ.get(token_key) if token_key else None
        if env_token:
            run_cfg["token"] = env_token
        else:
            console.print(f"[red]No token configured for {server_name}.[/red]")
            console.print(
                f"[dim]Run /mcp login {server_name} to authenticate, or "
                f"set {token_key} in your environment.[/dim]"
            )
            return

    if srv_config and srv_config.requires_node:
        npx_path = shutil.which("npx")
        if npx_path is None:
            console.print("[red]npx is required but not found. Install Node.js: https://nodejs.org/[/red]")
            return
        console.print(f"[dim]Found npx: {npx_path}[/dim]")

    if server_name == "stackoverflow":
        console.print()
        console.print("[bold cyan]Stack Overflow MCP uses browser-based OAuth.[/bold cyan]")
        console.print("[dim]A browser window will open for you to log in to Stack Overflow.[/dim]")
        console.print("[dim]After authentication, the MCP server will start.[/dim]")
        console.print()

    if server_name == "filesystem":
        dir_args = run_cfg.get("args", [])
        dirs = [
            a for a in dir_args
            if a not in ("-y", "@modelcontextprotocol/server-filesystem")
            and not a.startswith("-")
        ]
        if not dirs:
            dirs = ["."]

        resolved_dirs = []
        for d in dirs:
            p = (Path.cwd() / d).resolve() if not Path(d).is_absolute() else Path(d).resolve()
            if p.exists() and p.is_dir():
                resolved_dirs.append(str(p))
            else:
                console.print(f"[yellow]⚠ Directory not found: {d} → {p}[/yellow]")

        if not resolved_dirs:
            console.print("[red]No valid directories configured for filesystem MCP.[/red]")
            console.print("[dim]Set allowed directories via .haney/config.json → mcp.servers.filesystem.args[/dim]")
            return

        console.print(f"[dim]Filesystem access scoped to: {', '.join(resolved_dirs)}[/dim]")
        console.print("[bold yellow]🔒 Reminder:[/bold yellow] The filesystem MCP can access ANY file within the allowed directories — not just project files.")
        console.print()

    try:
        server = mcp_mgr.connect(server_name, run_cfg)
    except Exception as exc:
        console.print(f"[red]Failed to connect to {server_name}: {exc}[/red]")
        return

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
    console.print(f"[bold green]✓[/bold green] Connected to {server_name} MCP — {tools_count} tool(s) available.")


# ── /mcp disconnect ──────────────────────────────────────────────────────────

def cmd_mcp_disconnect(console: Console, args: list[str]) -> None:
    """Disconnect from an MCP server.

    Usage: /mcp disconnect <server>
    """
    mcp_mgr = get_mcp_manager()
    if mcp_mgr is None:
        console.print("[red]MCP manager not available.[/red]")
        return

    if not args:
        connected = mcp_mgr.get_connected_servers()
        if not connected:
            console.print("[yellow]No MCP servers are connected.[/yellow]")
            return
        for name in list(connected):
            mcp_mgr.disconnect(name)
            console.print(f"[dim]Disconnected from {name}.[/dim]")
        console.print("[bold green]✓[/bold green] All MCP servers disconnected.")
        return

    server_name = args[0].lower().strip()

    if not mcp_mgr.is_connected(server_name):
        console.print(f"[yellow]{server_name} is not connected.[/yellow]")
        return

    mcp_mgr.disconnect(server_name)
    console.print(f"[bold green]✓[/bold green] Disconnected from [bold]{server_name}[/bold] MCP.")

    cfg = load_config(Path.cwd())
    servers = cfg.get("mcp", {}).get("servers", {})
    if server_name in servers:
        servers[server_name]["enabled"] = False
        save_config(cfg, Path.cwd())


# ── /mcp status ──────────────────────────────────────────────────────────────

def cmd_mcp_status(console: Console, args: list[str]) -> None:
    """Show MCP connection status and available tools.

    Usage: /mcp status
    """
    mcp_mgr = get_mcp_manager()
    if mcp_mgr is None:
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

    connected = mcp_mgr.get_connected_servers()
    table.add_row("Connected Servers", ", ".join(connected) if connected else "[dim]none[/dim]")
    table.add_row("Total MCP Tools", str(mcp_mgr.get_tool_count()))

    console.print(table)

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

            if is_conn and mcp_mgr._servers.get(name):
                tool_count = len(mcp_mgr._servers[name].tool_defs)

            detail_table.add_row(
                name,
                "[green]✓[/green]" if has_token else "[yellow]✗[/yellow]",
                "[green]Yes[/green]" if is_conn else "[dim]No[/dim]",
                str(tool_count) if is_conn else "—",
            )

        console.print(detail_table)

    configured = set(servers_cfg.keys()) if servers_cfg else set()
    unconfigured = set(MCP_SERVERS.keys()) - configured
    if unconfigured:
        console.print(
            f"\n[dim]Not configured: {', '.join(sorted(unconfigured))}. "
            "Use /mcp login <server> to set up.[/dim]"
        )
