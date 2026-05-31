# Memory System

Haney's memory system uses two files with distinct purposes and lifecycles. Both live inside `.haney/` — they are Haney-managed, not user-committed.

## File Overview

| File | Location | Purpose | Managed by | Lifecycle |
|---|---|---|---|---|
| `memory.md` | `.haney/memory.md` | Long-term project knowledge | `/remember` (user) | Survives sessions |
| `summary.md` | `.haney/summary.md` | Compressed conversation summary | `/compact` (LLM) | Regenerated on demand |

## memory.md — Long-Term Memory

### Purpose

Stores persistent project knowledge that should survive across sessions:

- Preferred frameworks and libraries
- Coding conventions and style preferences
- Architecture decisions and rationale
- User preferences and constraints
- Important project-specific notes

### Management

**Append via `/remember`:**

```bash
/remember Use FastAPI with async endpoints
/remember Prefer uv over pip for dependency management
/remember All API routes require JWT authentication
```

Each `/remember` command appends a bullet point. Existing entries are never overwritten. If the file doesn't exist, it's created with a `# Project Memory` header.

**Format:**

```markdown
# Project Memory

This file stores long-term project memory for Haney.

Add notes, preferences, conventions, and other persistent context here.

* Use FastAPI with async endpoints
* Prefer uv over pip for dependency management
* All API routes require JWT authentication
```

### Context Injection

`memory.md` is loaded by `ProjectContextManager` as a high-priority file (priority 2, after `summary.md`). Its full content is injected into every LLM request's system prompt.

### Safety

- `/compact` never modifies `memory.md`
- `/remember` only appends — never deletes or overwrites
- Users can manually edit `memory.md` with any text editor

## summary.md — Conversation Summary

### Purpose

Stores a compressed representation of the current conversation state. Includes:

- Completed work
- Important decisions made during the conversation
- Current project architecture as understood by the model
- Open tasks and known issues

### Management

**Generated via `/compact`:**

```bash
/compact
```

The compact workflow:

1. Gather conversation history (last 40 messages), current `memory.md`, and previous `summary.md`
2. Send to the active LLM with a summarization prompt: *"Generate a concise project summary covering completed work, important decisions, current architecture, open tasks, and known issues. Keep under 1000 words."*
3. Write the result to `.haney/summary.md` (overwrites previous)
4. Truncate in-memory conversation to the last 10 messages
5. Reload project context to pick up the new summary
6. Display reduction metrics

**Display via `/summary`:**

```bash
/summary
```

Reads and displays the current `summary.md` content. No LLM call required.

### Context Injection

`summary.md` is loaded by `ProjectContextManager` as a high-priority file (priority 1, highest). It is injected at the top of the project context preamble in every LLM request.

### Lifecycle

- Generated fresh on each `/compact`
- Overwritten — not appended
- Does not persist across sessions in the same way as `memory.md` (regenerated when needed)
- Serves as a "state checkpoint" for long conversations

## How They Work Together

```
Session start
  │
  ├─ memory.md loaded (persistent knowledge)
  ├─ summary.md loaded (previous compact state, if exists)
  │
  ▼
Conversation proceeds
  │
  ├─ User adds context: /remember "Use PostgreSQL"
  │   └─ memory.md updated
  │
  ├─ Context grows too large
  │   └─ User runs /compact
  │       ├─ LLM reads memory.md + conversation
  │       ├─ Generates new summary.md
  │       ├─ Conversation truncated to last 10 messages
  │       └─ New summary injected into future context
  │
  ▼
Session ends
  │
  ├─ memory.md persists ✓
  └─ summary.md persists ✓ (used next session)
```

## Design Rationale

**Why two files instead of one?**

Memory and summary serve different purposes. Memory is user-curated, long-lived, and append-only. Summary is LLM-generated, ephemeral, and overwritten. Conflating them would make both less useful.

**Why `.haney/` instead of project root?**

These are Haney-internal files. They shouldn't clutter the project root or be accidentally committed. Only user-owned files (`plan.md`, `README.md`) belong at root.

**Why Markdown?**

Human-readable, editable in any text editor, renders well in GitHub and documentation tools. No custom format to learn.

**Why not vector embeddings?**

Haney is intentionally vector-free. Memory and summary are injected as raw text into the system prompt. This keeps the architecture simple, transparent, and cost-effective.
