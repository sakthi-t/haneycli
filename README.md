# Haney

A transparent, configuration-driven terminal AI coding assistant.

Built with Python, [Typer](https://typer.tiangolo.com/), [Rich](https://github.com/Textualize/rich), and [LiteLLM](https://github.com/BerriAI/litellm).

Haney is named after an apartment cat. She helps developers build useful things.

```
 /\_/\
( o.o )
 > ^ <

Haney Meow!
```

---

## What makes Haney different

Most coding agents are black boxes. Haney is **transparent by design** — every tool call, every permission, every config value is visible and controllable. No hidden limits. No magic prompts. Just a clean terminal interface with full control.

| Principle | How Haney delivers it |
|---|---|
| **Transparency** | Streamed LLM output, visible tool calls, per-message cost tracking |
| **Configurability** | All behavior driven by `.haney/config.json` — no hardcoded limits |
| **Safety** | PLAN/EDIT modes, ASK/SAVE/AUTO permissions, trash-based deletion |
| **Local-first** | Project files, session archives, memory — all stored in `.haney/` |
| **Provider-agnostic** | LiteLLM routes to 6+ providers with unified thinking modes |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                       Terminal                          │
│  ┌───────────────────────────────────────────────────┐  │
│  │              Conversation Output                  │  │
│  │  (streamed Markdown, tool results, errors)        │  │
│  └───────────────────────────────────────────────────┘  │
│  ─────────── Model: gpt-5.4  Think: high  ... ────────  │
│  [💾 save | edit] Haney > _                             │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                     ChatSession                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │ Project  │  │  File    │  │   Tool Manager        │  │
│  │ Context  │  │ Context  │  │  (approval + guard)   │  │
│  └──────────┘  └──────────┘  └──────────────────────┘  │
│                            │                           │
│                     LiteLLM ◄── tools                  │
│                            │                           │
│              ┌─────────────┼─────────────┐             │
│              ▼             ▼             ▼             │
│          OpenAI      DeepSeek      Anthropic           │
└─────────────────────────────────────────────────────────┘
```

### File structure

```
haneycli/
├── app.py                      # Entry point
├── requirements.txt
├── haney/
│   ├── cli.py                  # Typer CLI app
│   ├── chat.py                 # Read-eval loop + composer
│   ├── commands.py             # 27 slash-command handlers
│   ├── llm.py                  # ChatSession + streaming
│   ├── providers.py            # Provider registry + live model fetch
│   ├── config_bootstrap.py     # Single-source config schema
│   ├── project_context.py      # Project file discovery + injection
│   ├── file_context.py         # @file attachment parsing + loading
│   ├── session_manager.py      # Session lifecycle + persistence
│   ├── search.py               # Exa search integration
│   ├── thinking_manager.py     # Unified thinking mode abstraction
│   ├── mode_manager.py         # PLAN/EDIT mode guard
│   ├── permission_manager.py   # ASK/SAVE/AUTO approval modes
│   ├── setup.py                # First-run wizard + file templates
│   ├── banner.py               # Cat ASCII art
│   ├── config.py               # Constants
│   ├── tools/
│   │   ├── file_tools.py       # Read, write, edit, rename, trash
│   │   ├── shell_tools.py      # Safe command execution
│   │   └── tool_manager.py     # Tool registry + LiteLLM integration
│   └── ui/
│       └── composer.py         # Sticky input + status bar
└── .haney/
    ├── config.json             # All configuration
    ├── system.md               # System prompt
    ├── sessions/               # Archived sessions
    ├── trash/                  # Safe-deleted files
    └── help.md
```

---

## Installation

```bash
# From source
git clone https://github.com/your-org/haney.git
cd haneycli

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python app.py
```

```bash
# Planned: PyPI
pip install haney
```

---

## Quick Start

```
$ python app.py

 /\_/\
( o.o )
 > ^ <

Haney Meow!

Session: 2026-05-31-001  Type /help for commands. Type /exit to quit.

[💾 save | edit] Haney > /login openai
Enter your OpenAI API key: ••••••••••••••••••••••
✓ Logged into OpenAI

[❓ ask | plan] Haney > /model gpt-5.4
✓ Active model set to gpt-5.4

[❓ ask | plan] Haney > /edit
Mode changed to EDIT.

[💾 save | edit] Haney > explain Python decorators

A Python decorator is a function that wraps another function
to modify its behavior without changing source code...

[❓ ask | edit] Haney > @README.md summarize this
  ✓ README.md (2.9 KB, ~713 tokens)

This README describes Haney, a terminal-based AI coding
assistant built with Python, Typer, Rich, and LiteLLM...

[❓ ask | edit] Haney > /compact
Compacting conversation…
✓ summary.md updated
Estimated reduction: 78%

[❓ ask | edit] Haney > /exit
Session saved: 2026-05-31-001.json
```

---

## Features

### Multi-provider support

Six providers through LiteLLM — no vendor lock-in.

| Provider | Models |
|---|---|
| OpenAI | gpt-5.4, gpt-4o, o3, o4-mini, gpt-4.1, ... |
| Anthropic | claude-sonnet-4, claude-opus-4, claude-3.5-haiku, ... |
| DeepSeek | deepseek-chat, deepseek-reasoner |
| Gemini | gemini-2.5-flash, gemini-2.5-pro, ... |
| Groq | llama-3.3-70b, mixtral-8x7b, ... |
| OpenRouter | 200+ models, unified API |

Models are fetched live from each provider's API — no stale hardcoded lists.

```bash
/login openai          # Connect a provider
/models                # List live models
/model gpt-5.4         # Select a model
/provider              # Show connection status
```

### Thinking modes

Unified reasoning abstraction across all providers. No need to learn provider-specific settings.

```bash
/think off             # Temperature 0, deterministic
/think low             # Temperature 0.2
/think medium          # Default
/think high            # Extended reasoning (reasoning_effort=high for OpenAI)
```

### Plan Mode & Edit Mode

**PLAN** (default) — discuss, analyze, plan. All write tools blocked.

**EDIT** — full tool access with approval flow.

```bash
/plan                  # Switch to PLAN
/edit                  # Switch to EDIT
/mode                  # Show current mode
```

In PLAN mode, the LLM only sees `read_file` and `list_directory`. Write tools don't appear as options.

### Permission modes

Three approval levels for tool execution:

```bash
/permission ask        # Prompt for every modifying action (default)
/permission save       # Remember approvals for the session
/permission auto       # Auto-approve all non-dangerous tools
```

Dangerous shell commands (`rm`, `sudo`, `shutdown`) and path escapes are always blocked — even in AUTO mode.

### Project awareness

Haney automatically discovers and injects project files into every LLM request:

| Priority | File | Purpose |
|---|---|---|
| 1 | `summary.md` | Compressed conversation summary |
| 2 | `memory.md` | Long-term project knowledge |
| 3 | `plan.md` | Project plan and architecture |
| 4 | `README.md` | Project documentation |

```bash
/init                  # Generate starter files
/reload                # Re-scan project
/project               # Show loaded/missing files
/context               # Context size and health
```

### File attachments

Attach files with `@` syntax — they're automatically loaded and injected into context.

```bash
@main.py               # Single file
@app.py @README.md     # Multiple files
@.haney/system.md      # Nested paths
@src/utils/helper.py   # Deep paths
```

119 file extensions supported — Python, JS, TS, Go, Rust, HTML, CSS, YAML, Dockerfile, SQL, and more. Images show metadata (dimensions, format).

Token estimation and configurable limits prevent context overflow.

```bash
/attachments           # List currently attached files
```

### Safe tool system

All file operations are path-constrained to the project root.

| Tool | Safety |
|---|---|
| `read_file` | Auto-approved, read-only |
| `write_file` | Confirmation + PLAN guard |
| `edit_file` | Confirmation + diff preview |
| `rename_file` | Confirmation + path safety |
| `delete_file` | Moves to `.haney/trash/` — never permanent |
| `list_directory` | Auto-approved, read-only |
| `run_shell_command` | Whitelist + blacklist + confirmation |

```bash
/trash                 # List trashed files
/restore filename      # Recover from trash
```

Dangerous commands blocked: `rm`, `sudo`, `shutdown`, `reboot`, `mkfs`, `chmod 777`, pipe-to-shell, and more.

### Memory system

Two files for different purposes:

| File | Purpose | Persistence |
|---|---|---|
| `memory.md` | Long-term project preferences, conventions, decisions | Survives sessions |
| `summary.md` | Compressed conversation history | Regenerated via `/compact` |

```bash
/remember Use FastAPI for this project    # Append to memory.md
/summary                                   # Display current summary
/compact                                   # Generate summary + compact history
```

Memory survives across sessions. Summary is regenerated on demand.

### Compact mode

Reduces conversation context by generating a summary and truncating old messages.

```bash
/compact
```

```
Compacting conversation…
✓ summary.md updated

┌──────────────────────┬────────┐
│ Messages before      │     42 │
│ Messages after       │     10 │
│ Tokens before        │ ~8,500 │
│ Tokens after         │ ~1,200 │
│ Estimated reduction  │    86% │
└──────────────────────┴────────┘
```

### Session management

Every session is automatically saved to `.haney/sessions/` as timestamped JSON with full message history, token counts, and cost.

```bash
/history               # Recent sessions (read-only — never loaded)
/session               # Current session ID, provider, model, cost
/stats                 # Token metrics + per-call averages
```

### Rich terminal interface

Styled composer area with live status information:

```
─────────────────────────────────────────────────────────────────
Model: gpt-5.4  Think: high  Mode: edit  Perm: save  Search: on  Cost: $0.013  Ctx: 3k
─────────────────────────────────────────────────────────────────

[💾 save | edit] Haney > _
```

- LLM responses **stream live** as Markdown
- Tool calls show inline status (`⚙ Calling 2 tool(s)…`)
- Status bar updates automatically on mode/provider changes
- Configurable bottom padding and visibility

### Internet search

Exa integration for automatic web search enrichment:

```bash
/login exa             # Set Exa API key
```

When enabled, Haney searches Exa before each LLM call and injects results as context. The model decides whether to reference them.

```json
{ "web_search": true }
```

---

## Configuration

Haney is **configuration-driven**. Every operational limit, mode, and behavior is defined in `.haney/config.json` — nothing is hardcoded in source.

```json
{
  "active_provider": "openai",
  "active_model": "gpt-5.4",
  "mode": "edit",
  "thinking_mode": "high",
  "permission_mode": "save",
  "web_search": true,
  "search_provider": "exa",
  "max_tool_calls": 200,
  "max_attachment_tokens": 10000,
  "max_context_tokens": null,
  "ui": {
    "sticky_input": true,
    "input_bottom_padding": 2,
    "show_status_bar": true
  }
}
```

Missing keys are auto-populated with defaults on startup. `null` means unlimited.

---

## Commands reference

### Provider & Model

| Command | Description |
|---|---|
| `/login <provider>` | Connect an LLM provider or Exa search |
| `/logout [provider]` | Disconnect from a provider |
| `/models [provider]` | List all available models (live-fetched) |
| `/model [name]` | Show or set the active model |
| `/provider` | Show connection status + masked API key |

### Thinking & Execution

| Command | Description |
|---|---|
| `/think [off\|low\|medium\|high]` | Show or set thinking mode |
| `/plan` | Switch to PLAN mode (discussion only) |
| `/edit` | Switch to EDIT mode (tools enabled) |
| `/mode` | Show current execution mode |
| `/permission [ask\|save\|auto]` | Set approval mode |

### Project

| Command | Description |
|---|---|
| `/project` | Show project status and loaded files |
| `/reload` | Re-scan project files |
| `/context` | Show context size and health |
| `/init` | Generate starter project files |

### Files & Tools

| Command | Description |
|---|---|
| `/trash` | List files in trash |
| `/restore <file>` | Restore file from trash |
| `/attachments` | Show currently attached files |

### Session & Memory

| Command | Description |
|---|---|
| `/history` | List recent sessions (read-only) |
| `/session` | Current session info |
| `/stats` | Token and cost metrics |
| `/remember <text>` | Append to memory.md |
| `/summary` | Display current summary |
| `/compact` | Compact conversation + update summary |

### System

| Command | Description |
|---|---|
| `/help` | Show all commands |
| `/version` | Show Haney version |
| `/status` | Full runtime status |
| `/clear` | Clear screen + attachments |
| `/exit` | Exit and save session |

---

## Philosophy

Haney is built on a few core beliefs about developer tools:

**Transparency.** You should see what your AI is doing — streamed output, visible tool calls, tracked costs. No black boxes.

**Configurability.** Operational behavior belongs in config files, not buried in source code. Change limits, modes, and providers without touching Python.

**Developer-first.** The terminal is the developer's home. Haney stays there — no browser, no Electron, no distraction.

**Local-first.** Project context, session history, memory — all stored locally in `.haney/`. No cloud dependency for core features.

**Practical.** Haney doesn't try to be an autonomous agent by default. PLAN mode keeps discussions safe. EDIT mode enables real work. You decide when to cross that line.

---

## Roadmap

- MCP (Model Context Protocol) support
- Autonomous agent workflows
- Additional search providers (Tavily, Brave)
- Voice input support
- Git integration (PR review, commit messages)
- PyPI distribution

---

*"Please feed stray cats and dogs whenever possible. Small acts of kindness save lives."*

— Sakthivel T.
