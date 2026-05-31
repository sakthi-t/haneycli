# Tool System

Haney's tool system enables the LLM to read, write, edit, and manage files — and execute safe shell commands — within the project workspace. Every modifying operation goes through a multi-layered safety pipeline.

## Tool Architecture

```
LLM requests tool
  │
  ▼
ToolManager.execute_tool_call(name, args)
  │
  ├─ 1. Handler lookup          → Unknown tool? Error.
  ├─ 2. Mode guard (PLAN/EDIT)  → PLAN mode? Block write tools.
  ├─ 3. Permission check        → ASK/SAVE/AUTO approval
  ├─ 4. User confirmation       → Rich panel + [y/n] prompt
  └─ 5. Tool execution          → file_tools.py or shell_tools.py
       │
       ▼
  Result formatted for LLM → fed back to conversation
```

## Available Tools

### File Tools

| Tool | Description | Safety Level | PLAN Allowed |
|---|---|---|---|
| `read_file` | Read a file's contents. Returns text with line count. | Read | ✅ |
| `write_file` | Create or overwrite a file. Creates parent directories. | Write | ❌ |
| `edit_file` | Replace text in a file using exact string match. Shows diff. | Write | ❌ |
| `rename_file` | Rename or move a file within the project. | Write | ❌ |
| `delete_file` | Move a file to `.haney/trash/`. Never permanently deletes. | Write | ❌ |
| `list_directory` | List files and directories with sizes. | Read | ✅ |

### Shell Tool

| Tool | Description | Safety Level | PLAN Allowed |
|---|---|---|---|
| `run_shell_command` | Execute a safe shell command. Whitelist + blacklist enforced. | Write | ❌ |

## Safety Layers

### Layer 1: Path Containment

All file paths are resolved relative to the project root. Any path that escapes the project (e.g., `../../../etc/passwd`) is rejected with a `ValueError`. This check runs in `_resolve_safe()` before any file operation.

### Layer 2: Mode Guard (PLAN/EDIT)

In PLAN mode, the LLM only sees `read_file` and `list_directory` as available tools. Write tools (`write_file`, `edit_file`, `rename_file`, `delete_file`, `run_shell_command`) are filtered from the tool definitions before they reach the model.

Even if a write tool somehow reaches execution, the mode guard at `ToolManager.execute_tool_call()` blocks it:

```
⛔ You are currently in PLAN mode. Switch to EDIT mode using /edit.
```

### Layer 3: Permission Check (ASK/SAVE/AUTO)

Before any modifying tool executes, the permission manager determines whether user confirmation is needed:

| Mode | Read Tools | Write Tools |
|---|---|---|
| ASK | Auto-approved | Prompt every time |
| SAVE | Auto-approved | Prompt once, then remember |
| AUTO | Auto-approved | Auto-approved |

### Layer 4: Shell Safety

Shell commands go through two checks:

**Whitelist:** Only commands in the allowed set can run. Base commands include `pwd`, `ls`, `cat`, `grep`, `echo`, `git`, `python`, `pip`, etc.

**Blacklist:** Dangerous patterns are blocked regardless of the base command. Examples:

- `rm`, `rm -rf`
- `sudo`, `shutdown`, `reboot`
- `mkfs`, `format`, `dd`
- `chmod 777`
- `wget ... | sh`, `curl ... | sh`
- `>` redirects to `/dev/`
- `kill`, `fdisk`, `mount`, `iptables`

Blocked commands return immediately without execution:

```
Blocked: 'rm -rf /' may be destructive.
```

### Layer 5: Trash System

`delete_file` never permanently removes files. Instead:

1. `.haney/trash/` directory is created if missing
2. File is moved (not copied) to trash
3. Name collisions are handled with numeric suffixes (`file.py` → `file_1.py`)

Recovery:

```bash
/trash                    # List trashed files
/restore old_file.py      # Move back to project root
```

## Tool Definitions for LiteLLM

Tools are exposed to the LLM via LiteLLM's native tool-calling API. Each tool has a JSON Schema definition:

```json
{
  "type": "function",
  "function": {
    "name": "write_file",
    "description": "Create or overwrite a file. Requires user confirmation.",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {"type": "string", "description": "Relative path for the new file."},
        "content": {"type": "string", "description": "Content to write to the file."}
      },
      "required": ["path", "content"]
    }
  }
}
```

In PLAN mode, only `read_file` and `list_directory` definitions are passed to LiteLLM.

## Approval UI

When a tool requires confirmation, a Rich panel displays the action:

```
╭─ Tool Request — write_file ───────────────────────────────╮
│ Create: main.py                                            │
│                                                            │
│ Size: 5045 chars, 87 lines                                 │
╰───────────────────────────────────────────────────────────╯
Proceed? [y/n] (y):
```

For edits, the diff is shown:

```
╭─ Tool Request — edit_file ────────────────────────────────╮
│ Modify: main.py                                            │
│                                                            │
│ Find:                                                      │
│   def old_function():                                      │
│                                                            │
│ Replace with:                                              │
│   def new_function():                                      │
╰───────────────────────────────────────────────────────────╯
Proceed? [y/n] (y):
```

## Tool Execution Loop

When the LLM returns tool calls, Haney enters a tool execution loop:

1. Stream completion, accumulate tool calls
2. Display `⚙ Calling N tool(s)…`
3. For each tool: mode guard → permission check → approval → execute
4. Append tool results as `"role": "tool"` messages
5. Re-call the LLM with tool results in context
6. Continue until no more tool calls or `max_tool_calls` limit reached
7. Stream final answer

The loop limit is configurable via `max_tool_calls` in config.json (`null` = unlimited).

## Design Rationale

**Why separate read and write safety levels?**

Reading is always safe. Writing requires user trust. Separating them means PLAN mode users can explore freely while EDIT mode users get the tools they need.

**Why trash instead of permanent delete?**

Accidents happen. Trash provides a safety net. Users recover files with `/restore`. No data is ever lost without explicit user action.

**Why whitelist + blacklist for shell?**

A whitelist alone is too restrictive (blocks useful commands). A blacklist alone is too permissive (misses dangerous variants). Combined, they provide both flexibility and safety.
