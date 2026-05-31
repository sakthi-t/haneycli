# Configuration

Haney is configuration-driven. Every operational limit, mode, and behavior setting lives in `.haney/config.json`. Nothing is hardcoded in Python source files.

## Philosophy

1. **Single source of truth.** All configurable values are defined in `config_bootstrap.py`'s `CONFIG_SCHEMA` dict. This is the canonical reference.
2. **Auto-population.** On every startup, `bootstrap_config()` reads the current config file and adds any missing keys with defaults. Users never need to manually add new keys.
3. **Never overwrite.** Existing values are preserved. Only missing keys get defaults.
4. **Null means unlimited.** Numeric limits set to `null` are treated as "no limit enforced."
5. **No hidden limits.** Source code reads config at runtime — there are no hardcoded fallback values buried in functions.

## Config File Location

```
.haney/config.json
```

Created automatically during first-run setup or first startup. The `.haney/` directory lives at the project root.

## Full Schema

```json
{
  "_comment": "Haney configuration. Set API keys via /login <provider>.",
  "_exa_comment": "EXA_API_KEY can be set via /login exa or the EXA_API_KEY env var.",

  "active_provider": null,
  "active_model": null,
  "providers": {},

  "mode": "plan",
  "thinking_mode": "medium",
  "permission_mode": "ask",

  "web_search": true,
  "search_provider": "exa",
  "search": {},

  "max_tool_calls": 20,
  "max_attachment_tokens": 10000,
  "max_context_tokens": null,

  "approval_mode": "write_only",

  "ui": {
    "sticky_input": true,
    "input_bottom_padding": 2,
    "show_status_bar": true
  }
}
```

## Key Reference

### Provider Settings

| Key | Type | Default | Description |
|---|---|---|---|
| `active_provider` | string\|null | `null` | Currently connected provider (`openai`, `deepseek`, etc.) |
| `active_model` | string\|null | `null` | Currently selected model (`gpt-5.4`, `deepseek-chat`, etc.) |
| `providers` | object | `{}` | Stored API keys per provider. Managed by `/login` / `/logout`. |

### Mode Settings

| Key | Type | Default | Description |
|---|---|---|---|
| `mode` | string | `"plan"` | Execution mode: `"plan"` (discussion only) or `"edit"` (tools enabled) |
| `thinking_mode` | string | `"medium"` | Reasoning level: `"off"`, `"low"`, `"medium"`, `"high"` |
| `permission_mode` | string | `"ask"` | Approval mode: `"ask"`, `"save"`, `"auto"` |

### Search Settings

| Key | Type | Default | Description |
|---|---|---|---|
| `web_search` | boolean | `true` | Enable/disable automatic web search enrichment |
| `search_provider` | string | `"exa"` | Search backend (currently only `"exa"`) |
| `search` | object | `{}` | Search provider credentials. `exa_api_key` stored by `/login exa`. |

### Limit Settings

| Key | Type | Default | Description |
|---|---|---|---|
| `max_tool_calls` | int\|null | `20` | Maximum sequential tool calls per user message. `null` = unlimited. |
| `max_attachment_tokens` | int\|null | `10000` | Maximum tokens for attached file content. `null` = unlimited. |
| `max_context_tokens` | int\|null | `null` | Maximum total context tokens. `null` = unlimited. |

### Approval Settings

| Key | Type | Default | Description |
|---|---|---|---|
| `approval_mode` | string | `"write_only"` | Legacy approval mode. Superseded by `permission_mode`. |

### UI Settings

| Key | Type | Default | Description |
|---|---|---|---|
| `ui.sticky_input` | boolean | `true` | Enable the sticky composer area with status bar. |
| `ui.input_bottom_padding` | int | `2` | Blank rows above the composer separator. |
| `ui.show_status_bar` | boolean | `true` | Show the model/think/mode/perm/cost/context status line. |

## API Key Management

API keys can be set in three ways (checked in order):

1. **Config file** — via `/login <provider>`. Stored in `providers.<name>.api_key`.
2. **Environment variables** — `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, etc.
3. **Exa search** — via `/login exa`. Stored in `search.exa_api_key`. Falls back to `EXA_API_KEY` env var.

Keys stored in config are masked when displayed (e.g., `sk-pr...Xwx0A`).

## Example: Production Config

```json
{
  "_comment": "Haney configuration. Set API keys via /login <provider>.",
  "_exa_comment": "EXA_API_KEY can be set via /login exa or the EXA_API_KEY env var.",
  "active_provider": "openai",
  "active_model": "gpt-5.4",
  "providers": {
    "openai": {
      "api_key": "sk-proj-..."
    }
  },
  "mode": "edit",
  "thinking_mode": "high",
  "permission_mode": "save",
  "web_search": true,
  "search_provider": "exa",
  "search": {
    "exa_api_key": "..."
  },
  "max_tool_calls": 200,
  "max_attachment_tokens": 10000,
  "max_context_tokens": null,
  "approval_mode": "write_only",
  "ui": {
    "sticky_input": true,
    "input_bottom_padding": 2,
    "show_status_bar": true
  }
}
```

## Bootstrap Process

At every startup, `chat.py` calls:

```python
bootstrap_config(cwd, console)
```

This function:

1. Loads `.haney/config.json`
2. Iterates over `CONFIG_SCHEMA` (from `config_bootstrap.py`)
3. For each missing key, inserts the default value
4. If any keys were added, saves the file and prints a notice
5. Returns the complete config dict

This ensures backward compatibility: new Haney versions can add config keys without breaking existing installations.
