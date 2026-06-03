"""LiteLLM integration for Haney chat.

Provides the ChatSession class that manages conversation history,
loads the system prompt, calls LiteLLM for completions,
and optionally enriches context with Exa web search results.
"""

from __future__ import annotations

import logging
import warnings
import time
from pathlib import Path
from typing import Optional

# Suppress noisy LiteLLM import-time warnings before importing
logging.getLogger("LiteLLM").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message=".*PydanticSerializationUnexpectedValue.*", category=UserWarning)

import litellm

litellm.suppress_debug_info = True
litellm.set_verbose = False

from rich.console import Console
from rich.text import Text

from haney.config import HANEY_DIR
from haney.providers import (
    get_active_provider,
    get_api_key,
    get_active_model,
    load_config,
)
from haney.search import SearchManager
from haney.project_context import ProjectContextManager
from haney.file_context import FileContextManager
from haney.tools.tool_manager import ToolManager
from haney.session_manager import SessionManager
from haney.thinking_manager import get_thinking_mode, get_completion_params
from haney.mode_manager import get_mode
from haney.permission_manager import PermissionManager
from haney.mcp.server_manager import MCPServerManager
from haney.mcp.server_configs import get_server_config


class ChatSession:
    """Manages an in-memory conversation with an LLM via LiteLLM.

    Holds conversation history as a list of message dicts,
    handles loading the system prompt from .haney/system.md,
    and optionally enriches context with Exa web search results.
    """

    def __init__(
        self,
        console: Console,
        cwd: Path | None = None,
        project_ctx: ProjectContextManager | None = None,
        session_mgr: SessionManager | None = None,
        perm_mgr: PermissionManager | None = None,
        mcp_mgr: MCPServerManager | None = None,
    ) -> None:
        """Initialise a new chat session.

        Args:
            console: Rich Console for output.
            cwd: Working directory.
            project_ctx: ProjectContextManager.
            session_mgr: SessionManager for tracking.
            perm_mgr: PermissionManager for approval flow.
            mcp_mgr: Optional MCPServerManager for MCP tools.
        """
        self.console = console
        self.cwd = cwd or Path.cwd()
        self.messages: list[dict[str, str]] = []
        self._system_prompt: str | None = None
        self.search = SearchManager(console, self.cwd)
        self.project_ctx = project_ctx
        self.file_ctx = FileContextManager(self.cwd)
        self.session_mgr = session_mgr

        self.tool_ctx = ToolManager(console, self.cwd)
        if perm_mgr:
            self.tool_ctx.permissions = perm_mgr

        # ── MCP integration ───────────────────────────────────
        if mcp_mgr is None:
            self._init_mcp()
        else:
            self.tool_ctx.mcp_manager = mcp_mgr

    def _init_mcp(self) -> None:
        """Initialise MCP servers if enabled in config.

        Creates the MCPServerManager and connects to enabled servers.
        Links the manager to the ToolManager for tool discovery.
        """
        cfg = load_config(self.cwd)
        mcp_cfg = cfg.get("mcp", {})

        if not mcp_cfg.get("enabled", False):
            return

        try:
            mcp_mgr = MCPServerManager(cwd=self.cwd, console=self.console)
        except Exception:
            # MCP is optional; don't block startup
            return

        enabled_servers = mcp_cfg.get("servers", {})
        connected = False

        for srv_name, srv_cfg in enabled_servers.items():
            if not isinstance(srv_cfg, dict):
                continue
            if not srv_cfg.get("enabled", False):
                continue

            # Check if this server requires authentication
            srv_config = get_server_config(srv_name)
            needs_auth = srv_config.requires_auth if srv_config else True

            if needs_auth and not srv_cfg.get("token") and not srv_cfg.get("env"):
                continue  # No auth configured for a server that requires it

            try:
                mcp_mgr.connect(srv_name, srv_cfg)
                connected = True
            except Exception as exc:
                self.console.print(
                    f"[yellow]MCP server '{srv_name}' failed to connect: {exc}[/yellow]"
                )

        if connected:
            self.tool_ctx.mcp_manager = mcp_mgr

    @property
    def system_prompt(self) -> str:
        """Return the system prompt, loading from disk on first access."""
        if self._system_prompt is None:
            self._system_prompt = self._load_system_prompt()
        return self._system_prompt

    def _load_system_prompt(self) -> str:
        """Read the system prompt from .haney/system.md.

        Returns:
            System prompt text, or a default if the file is missing.
        """
        path = self.cwd / HANEY_DIR / "system.md"
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
        return "You are Haney, a helpful terminal-based AI coding assistant."

    def _get_active_config(self) -> tuple[str, str, str]:
        """Validate and return (provider, model, api_key).

        Raises:
            RuntimeError: If provider, model, or API key is missing.
        """
        provider = get_active_provider(self.cwd)
        if not provider:
            raise RuntimeError(
                "No active provider. Use /login <provider> to connect."
            )

        model = get_active_model(self.cwd)
        if not model:
            raise RuntimeError(
                "No active model. Use /model <name> to select one."
            )

        api_key = get_api_key(provider, self.cwd)
        if not api_key:
            raise RuntimeError(
                f"No API key found for {provider}. Use /login {provider}."
            )

        return provider, model, api_key

    def _build_litellm_model(self, provider: str, model: str) -> str:
        """Build the full LiteLLM model identifier."""
        return f"{provider}/{model}"

    def _build_messages(
        self, user_content: str, search_context: str | None = None
    ) -> list[dict[str, str]]:
        """Build the complete message list.

        Layers the system prompt, project context, optional web search
        results, conversation history, and the current user message.

        Args:
            user_content: The user's latest message.
            search_context: Optional web search results to inject.

        Returns:
            List of message dicts ready for litellm.completion.
        """
        # ── System prompt ─────────────────────────────────────
        current_mode = get_mode(self.cwd)
        mode_note = (
            f"\n\n**Current mode: {current_mode.upper()}.** "
            f"{'All tools are available.' if current_mode == 'edit' else 'Only read-only tools are available. Switch to EDIT with /edit.'}"
        )
        system_content = self.system_prompt + mode_note

        # ── Project context (injected automatically) ──────────
        if self.project_ctx is not None:
            preamble = self.project_ctx.build_context_preamble()
            if preamble:
                system_content = preamble + "\n\n---\n\n" + system_content

        # ── Attached file context ─────────────────────────────
        attach_preamble = self.file_ctx.build_context()
        if attach_preamble:
            system_content += "\n\n" + attach_preamble

        msgs: list[dict[str, str]] = [
            {"role": "system", "content": system_content},
        ]

        # ── Web search results ────────────────────────────────
        if search_context:
            msgs.append(
                {
                    "role": "system",
                    "content": (
                        "The following web search results may be relevant to "
                        "the user's question. Use them if they help; "
                        "ignore them otherwise:\n\n" + search_context
                    ),
                }
            )

        # ── Conversation history + current message ────────────
        msgs.extend(self.messages)
        msgs.append({"role": "user", "content": user_content})
        return msgs

    def send(self, user_input: str) -> str:
        """Send a user message to the LLM and return the response.

        Streams the final response live. During tool-calling rounds,
        shows a brief status line. Handles @file, search, context.
        """
        provider, model, api_key = self._get_active_config()
        litellm_model = self._build_litellm_model(provider, model)

        # ── Parse @file attachments ─────────────────────────
        attach_names = self.file_ctx.parse_attachments(user_input)
        clean_input = (
            self.file_ctx.strip_attachments(user_input) if attach_names else user_input
        )

        if attach_names:
            self.file_ctx.attach_files(attach_names, self.console)
            if not self.file_ctx.empty:
                self.file_ctx.display_summary(self.console)
            else:
                self.console.print(
                    "[dim]Tip: @file paths are relative to the project root. "
                    "Use @README.md or @.haney/system.md[/dim]"
                )

        # ── Web search enrichment ───────────────────────────
        search_context = None
        if self.search.available:
            search_context = self.search.search(clean_input or user_input)

        # ── Build messages ──────────────────────────────────
        messages = self._build_messages(clean_input, search_context)

        # ── Read tool-call limit from config ────────────────
        cfg = load_config(self.cwd)
        max_rounds = cfg.get("max_tool_calls")
        if max_rounds is None:
            max_rounds = 999

        # ── LLM call loop (stream final answer, brief tool rounds) ─
        start_time = time.monotonic()
        assistant_content = ""

        try:
            for _round in range(max_rounds):
                think_mode = get_thinking_mode(self.cwd)
                extra_params = get_completion_params(provider, think_mode)

                # ── Stream the LLM call ─────────────────────
                streamed_text, tool_calls, usage = self._stream_completion(
                    litellm_model, messages, api_key, extra_params,
                )

                # Track usage — fall back to estimation
                # if the provider didn't return usage in the stream
                if self.session_mgr:
                    prompt_tokens = usage.get("prompt_tokens", 0) if usage else 0
                    completion_tokens = usage.get("completion_tokens", 0) if usage else 0

                    if prompt_tokens == 0 and completion_tokens == 0:
                        # Estimate: char ÷ 4 for input, char ÷ 4 for output
                        prompt_tokens = sum(
                            len(m["content"]) // 4 for m in messages
                            if isinstance(m.get("content"), str)
                        )
                        completion_tokens = max(1, len(streamed_text) // 4)

                    self.session_mgr.record_usage(
                        model, prompt_tokens, completion_tokens,
                    )

                # No tool calls — final answer streamed live
                if not tool_calls:
                    assistant_content = streamed_text
                    break

                # ── Execute tool calls ────────────────────────
                messages.append({
                    "role": "assistant",
                    "content": streamed_text,
                    "tool_calls": tool_calls,
                })

                for tc in tool_calls:
                    tool_name = tc["function"]["name"]
                    try:
                        import json
                        args = json.loads(tc["function"]["arguments"])
                    except (json.JSONDecodeError, KeyError):
                        args = {}

                    result_str = self.tool_ctx.execute_tool_call(tool_name, args)

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result_str,
                    })

            else:
                assistant_content = streamed_text or "(Tool call limit reached.)"

        except litellm.exceptions.AuthenticationError:
            raise RuntimeError(
                f"Authentication failed for {provider}. Use /login {provider} to re-enter."
            )
        except litellm.exceptions.NotFoundError:
            raise RuntimeError(
                f"Model '{model}' not found. Use /models to see available models."
            )
        except litellm.exceptions.RateLimitError:
            raise RuntimeError(
                f"Rate limit exceeded for {provider}. Wait and try again."
            )
        except litellm.exceptions.APIConnectionError:
            raise RuntimeError(f"Cannot connect to {provider}. Check your network.")
        except litellm.exceptions.ServiceUnavailableError:
            raise RuntimeError(f"{provider} is unavailable. Try later.")
        except litellm.exceptions.APIError as exc:
            msg = exc.message if hasattr(exc, "message") else str(exc)
            raise RuntimeError(f"{provider} API error: {msg}")
        except litellm.exceptions.UnsupportedParamsError as exc:
            raise RuntimeError(f"Unsupported params for {provider}/{model}: {exc}")
        except Exception as exc:
            raise RuntimeError(f"Unexpected error from {provider}: {exc}")

        elapsed = time.monotonic() - start_time

        # Persist conversation
        self.messages.append({"role": "user", "content": clean_input})
        self.messages.append({"role": "assistant", "content": assistant_content})
        if self.session_mgr:
            self.session_mgr.record_message("user", clean_input)
            self.session_mgr.record_message("assistant", assistant_content)

        # Display response header
        extra_parts: list[str] = []
        if search_context:
            extra_parts.append("🔍")
        if attach_names:
            extra_parts.append(f"📎 ×{len(attach_names)}")
        extra = " " + " ".join(extra_parts) if extra_parts else ""
        self._display_response_header(provider, model, litellm_model + extra, elapsed)

        return assistant_content

    # ── Streaming helper ─────────────────────────────────────────────────

    def _stream_completion(
        self,
        litellm_model: str,
        messages: list[dict],
        api_key: str,
        extra_params: dict,
    ) -> tuple[str, list[dict], dict | None]:
        """Stream a completion and display content live via Rich.

        Returns (accumulated_text, tool_calls_list, usage_dict).
        """
        from rich.live import Live
        from rich.markdown import Markdown
        from rich.panel import Panel

        response = litellm.completion(
            model=litellm_model,
            messages=messages,
            api_key=api_key,
            tools=self.tool_ctx.tool_definitions,
            tool_choice="auto",
            stream=True,
            **extra_params,
        )

        collected = ""
        tool_call_chunks: dict[int, dict] = {}
        usage = None
        live = Live("", console=self.console, refresh_per_second=15, transient=False)
        live.start()

        try:
            for chunk in response:
                # Usage info (usually in the last chunk)
                if hasattr(chunk, "usage") and chunk.usage:
                    usage = {
                        "prompt_tokens": getattr(chunk.usage, "prompt_tokens", 0) or 0,
                        "completion_tokens": getattr(chunk.usage, "completion_tokens", 0) or 0,
                    }

                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                # Text content
                if delta.content:
                    collected += delta.content
                    live.update(Markdown(collected))

                # Tool calls (accumulated across chunks)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_call_chunks:
                            tool_call_chunks[idx] = {
                                "id": tc.id or "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        if tc.id:
                            tool_call_chunks[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_call_chunks[idx]["function"]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_call_chunks[idx]["function"]["arguments"] += tc.function.arguments
        finally:
            live.stop()

        tool_calls = list(tool_call_chunks.values()) if tool_call_chunks else []

        # If tools were called, show what happened
        if tool_calls:
            self.console.print(
                f"[dim]⚙ Calling {len(tool_calls)} tool(s)…[/dim]"
            )

        return collected, tool_calls, usage

    def _display_response_header(
        self, provider: str, model: str, litellm_model: str, elapsed: float,
    ) -> None:
        """Display a compact response header after streaming completes."""
        header = Text.assemble(
            ("Provider: ", "dim"),
            (f"{provider}  ", "bold cyan"),
            ("Model: ", "dim"),
            (f"{model}  ", "bold cyan"),
            ("Time: ", "dim"),
            (f"{elapsed:.1f}s", "bold green"),
        )
        self.console.print(header)

    def clear(self) -> None:
        """Clear conversation history and file attachments."""
        self.messages.clear()
        self.file_ctx.clear()
