# Commands Reference

Haney provides 27 slash-commands organized by category. All commands are prefixed with `/` and routed through `commands.py`'s dispatch function.

## Provider & Model

Commands for connecting LLM providers and selecting models.

| Command | Arguments | Description |
|---|---|---|
| `/login` | `<provider>` | Connect an LLM provider. Prompts for API key (masked). Supports: `openai`, `anthropic`, `deepseek`, `gemini`, `openrouter`, `groq`, `exa` |
| `/logout` | `[provider]` | Disconnect from a provider. Removes stored credentials. Defaults to active provider. |
| `/models` | `[provider]` | List all available models. Live-fetched from the API when logged in. Falls back to curated defaults. |
| `/model` | `[name]` | Show current model config (provider, model, thinking, search) or set a new model. |
| `/provider` | — | Show current provider status: name, API base, connection state, masked API key, active model. |

### Examples

```bash
/login openai                       # Connect to OpenAI
/login exa                          # Set Exa search API key
/logout                             # Disconnect active provider
/logout deepseek                    # Disconnect specific provider
/models                             # List OpenAI models (live)
/models anthropic                   # List Anthropic models
/model                              # Show current: Provider, Model, Thinking, Search
/model gpt-5.4                      # Switch to gpt-5.4
/provider                           # Full status table
```

## Thinking & Execution Modes

Commands for controlling reasoning effort and execution behavior.

| Command | Arguments | Description |
|---|---|---|
| `/think` | `[off\|low\|medium\|high]` | Show or set thinking mode. Unified abstraction across all providers. |
| `/plan` | — | Switch to PLAN mode. Discussion only — all write tools blocked. |
| `/edit` | — | Switch to EDIT mode. Full tool access with approval flow. |
| `/mode` | — | Show current execution mode and whether tool execution is enabled. |
| `/permission` | `[ask\|save\|auto]` | Show or set permission mode. Controls approval requirements. |

### Thinking Mode Details

| Mode | Effect |
|---|---|
| `off` | Temperature 0.0 — deterministic output |
| `low` | Temperature 0.2 — minimal variation |
| `medium` | Default — no special params |
| `high` | Extended reasoning. OpenAI: `reasoning_effort=high`. Anthropic: `thinking.budget_tokens=4000` |

### Permission Mode Details

| Mode | Behavior |
|---|---|
| `ask` | Prompt for every modifying action (default) |
| `save` | Prompt once per tool type, remember for the session. Resets on exit. |
| `auto` | Auto-approve all non-dangerous tools. Dangerous commands still blocked. |

### Examples

```bash
/think high                         # Enable extended reasoning
/think off                          # Deterministic mode
/plan                               # Enter PLAN mode
/edit                               # Enter EDIT mode
/mode                               # Show: PLAN or EDIT
/permission                         # Show current: ASK, SAVE, or AUTO
/permission save                    # Remember approvals this session
/permission auto                    # Auto-approve (use carefully)
```

## Project

Commands for project awareness and file management.

| Command | Arguments | Description |
|---|---|---|
| `/project` | — | Show project name, awareness status, loaded/missing files, context size. |
| `/reload` | — | Re-scan and reload all project files. Recalculates token estimates. |
| `/context` | — | Show loaded context: file sizes, token estimates, priority, health indicator. |
| `/init` | — | Generate starter project files: `plan.md`, `.haney/memory.md`, `.haney/summary.md`, `.haney/tasks.md`. |

### Examples

```bash
/project                            # Project status + loaded files
/reload                             # Refresh after editing plan.md
/context                            # Context table with health
/init                               # Create missing project files
```

## Files & Tools

Commands for the safe tool system and trash management.

| Command | Arguments | Description |
|---|---|---|
| `/trash` | — | List files in `.haney/trash/`. |
| `/restore` | `<filename>` | Restore a file from trash back to the project root. |
| `/attachments` | — | Show currently attached files with sizes and token estimates. |

### Examples

```bash
/trash                              # See deleted files
/restore old_config.py              # Recover a file
```

## Session & Memory

Commands for session management, memory, and conversation compaction.

| Command | Arguments | Description |
|---|---|---|
| `/history` | — | List recent sessions (ID, provider, model, messages, cost). Read-only. |
| `/session` | — | Current session: ID, provider, model, started time, messages, API calls, cost. |
| `/stats` | — | Token metrics: input, output, total, API calls, cost, per-call averages. |
| `/remember` | `<text>` | Append a bullet point to `.haney/memory.md`. |
| `/summary` | — | Display current `.haney/summary.md`. No LLM call required. |
| `/compact` | — | Compress conversation: generate summary via LLM, update `.haney/summary.md`, truncate history. |

### Examples

```bash
/history                            # Past sessions (never loaded)
/session                            # Current session info
/stats                              # Token + cost breakdown
/remember Use uv for dependencies   # Save to memory.md
/summary                            # Read summary.md
/compact                            # Compress + update summary
```

## System

General utility commands.

| Command | Arguments | Description |
|---|---|---|
| `/help` | — | Show all available commands with descriptions. |
| `/version` | — | Show Haney version. |
| `/status` | — | Full runtime status: provider, model, thinking, search, mode, session cost, tokens, API calls, messages, context size. |
| `/clear` | — | Clear terminal screen, conversation history, and file attachments. |
| `/exit` | — | Exit Haney gracefully. Saves session automatically. |

### Examples

```bash
/help                               # Full command list
/status                             # Complete runtime overview
/clear                              # Fresh start
/exit                               # Save and quit
```

## File Attachment Syntax

Not a command, but a core input mechanism. Use `@filename` in any chat message to attach files.

```
@main.py                   # Attach a file at project root
@app.py @README.md         # Multiple files
@.haney/system.md          # Nested paths
@src/utils/helper.py       # Deep paths
```

Attached files are stripped from the visible message, loaded into context, and injected into the LLM's system prompt. 119 file extensions supported.
