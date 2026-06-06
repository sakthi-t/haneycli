# MCP — Model Context Protocol

```
  ┌───────────────────────────────────────────────────┐
  │                     Haney                          │
  │   ┌─────────┐  ┌─────────┐  ┌───────────┐         │
  │   │ GitHub  │  │  MDN    │  │ Playwright│         │
  │   └────┬────┘  └────┬────┘  └─────┬─────┘         │
  │   ┌────┴────┐  ┌────┴────┐  ┌─────┴─────┐         │
  │   │ DuckGo  │  │   SO    │  │ LangChain │         │
  │   └────┬────┘  └────┬────┘  └─────┬─────┘         │
  │   ┌────┴────┐  ┌────┴────┐  ┌─────┴─────┐         │
  │   │   FS    │  │ SeqThink│  │   Notion  │         │
  │   └────┬────┘  └────┬────┘  └─────┬─────┘         │
  │   ┌────┴────┐           ┌─────────┴──────┐        │
  │   │ Tavily  │           │  mcp-remote    │        │
  │   └─────────┘           └────────────────┘        │
  │     10 servers · stdio + mcp-remote · JSON-RPC 2.0│
  └───────────────────────────────────────────────────┘
```

Haney connects to MCP servers as subprocesses over stdio using JSON-RPC 2.0.
Tools are namespaced as `mcp__<server>__<toolname>` and integrate with Haney's
permission system (ASK/SAVE/AUTO).

## Available Servers

| # | Server | Auth | Namespace |
|---|---|---|---|
| 1 | **GitHub** | OAuth PAT | `mcp__github__*` |
| 2 | **DuckDuckGo** | None | `mcp__duckduckgo__*` |
| 3 | **Stack Overflow** | None | `mcp__stackoverflow__*` |
| 4 | **MDN Web Docs** | None | `mcp__mdn__*` |
| 5 | **Filesystem** | None | `mcp__filesystem__*` |
| 6 | **Sequential Thinking** | None | `mcp__sequential-thinking__*` |
| 7 | **LangChain** | None | `mcp__langchain__*` |
| 8 | **Playwright** | None | `mcp__playwright__*` |
| 9 | **Tavily** | API Key | `mcp__tavily__*` |
| 10 | **Notion** | Integration Token | `mcp__notion__*` |

## Server Details

### GitHub
Repository management, issues, PRs, commits, code search, file operations.
```
/mcp login github       → OAuth device flow
/mcp connect github     → Start server
```

### DuckDuckGo
Anonymous web search — no API key, no tracking.
```
search("query")         → title, URL, snippet
fetch_content(url)      → clean text extraction
```

### Stack Overflow
Lexical search for questions, answers, and comments.
```
so_search("error handling in Rust")
get_content("SO_Q4965, SO_A4972")
```

### MDN Web Docs
Web documentation — CSS, JS, HTML, APIs, HTTP, browser compat.
```
mdn_search("grid layout")   → find docs
mdn_doc(path)               → full page
mdn_compat("css.properties.grid")
mdn_css("display")
mdn_http("headers")
```

> ⚠️ Experimental. `MOZ_OPT_OUT=1` set by default.

### Filesystem
Secure file operations constrained to allowed paths.
```
read_text_file, write_file, edit_file
list_directory, directory_tree, search_files
move_file, get_file_info
```

### Sequential Thinking
Structured step-by-step reasoning with revision tracking, branching,
and hypothesis verification.

### LangChain
LangChain / LangGraph documentation search.

### Playwright
Headless browser automation — navigation, screenshots, form filling,
network inspection, JavaScript evaluation.

### Tavily
AI-optimized web search and content extraction via mcp-remote (HTTP transport).
Requires an API key from [tavily.com](https://tavily.com).
```
/mcp login tavily        → Enter Tavily API key
/mcp connect tavily      → Start server
```

### Notion
Workspace integration — search pages, read/write databases,
manage comments, list users. Requires a Notion integration token.
```
/mcp login notion        → Enter Notion integration token
/mcp connect notion      → Start server
```

## Commands

| Command | Description |
|---|---|
| `/mcp login <server>` | Authenticate (GitHub OAuth, Tavily API key, Notion token) |
| `/mcp logout <server>` | Clear stored credentials |
| `/mcp connect <server>` | Start a server |
| `/mcp disconnect [name]` | Stop server(s) |
| `/mcp status` | Connected servers + tool count |
| `/mcp servers` | List all available servers |

## Architecture

```
Config (server_configs.py)
    │
    ▼
ServerManager ──→ Transport (subprocess stdio)
    │                  │
    │                  ▼
    │            Client (JSON-RPC 2.0)
    │                  │
    ▼                  ▼
ToolAdapter ←── MCP tools → LiteLLM schema
    │
    ▼
ToolManager ──→ LLM function calling
    │
    ▼
PermissionManager (ASK/SAVE/AUTO)
```

## Security

- MCP tools run in EDIT mode only (not available in PLAN mode)
- Full permission flow applies — ASK prompts, SAVE remembers, AUTO approves
- `extra_env` field on `MCPServerConfig` for per-server environment variables
- Credentials stored in `.haney/config.json` (never committed)
- Path-constrained filesystem operations
