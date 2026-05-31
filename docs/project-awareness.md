# Project Awareness

Haney automatically discovers and loads project files as context for every LLM interaction. This system ensures the model always has up-to-date knowledge of your project without manual effort.

## How It Works

At startup and on `/reload`, `ProjectContextManager` scans two locations:

| Location | Files | Owner |
|---|---|---|
| Project root | `plan.md`, `README.md` | User-created, committed to git |
| `.haney/` | `memory.md`, `summary.md`, `tasks.md` | Haney-managed |

Source files (`*.py`, `*.js`, `*.ts`, etc.) at the project root are also discovered and listed but not injected into context (to avoid token waste).

## Priority Order

When building the context preamble for the LLM, files are ordered by priority:

| Priority | File | Why first? |
|---|---|---|
| 1 | `summary.md` | Current conversation state — most relevant |
| 2 | `memory.md` | Persistent project knowledge |
| 3 | `plan.md` | Project roadmap and architecture |
| 4 | `README.md` | Project documentation |
| 5 | `architecture.md` | Architecture details (medium priority) |
| 6 | `tasks.md` | Task tracking (medium priority) |

## Context Injection Format

The preamble is injected into the system prompt as Markdown:

```markdown
## Project Context

**Project:** haneycli

### summary.md  (0.8 KB, ~200 tokens)

# Project Summary
...

### memory.md  (1.2 KB, ~300 tokens)

# Project Memory
...

### plan.md  (2.3 KB, ~580 tokens)

# haneycli — Project Plan
...

### README.md  (4.7 KB, ~1180 tokens)

# Haney
...
```

## Commands

### `/project`

Displays project status: name, awareness level, loaded files, missing files, context size, last reload time.

```
Project Status — haneycli
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ Setting          ┃ Value       ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ Project Name     │ haneycli    │
│ Project Awareness│ Enabled     │
│ Context Size     │ ~2,876      │
│ Last Reload      │ 2m ago      │
└──────────────────┴─────────────┘

Loaded Files:
  ✓ summary.md (0.8 KB)
  ✓ memory.md (1.2 KB)
  ✓ plan.md (2.3 KB)
  ✓ README.md (4.7 KB)
```

### `/reload`

Re-scans the project directory, refreshes the file cache, and recalculates token estimates.

```
Reloading project…
  ✓ summary.md
  ✓ memory.md
  ✓ plan.md
  ✓ README.md

Project context refreshed.
Context size: ~2,876 tokens
```

### `/context`

Shows detailed context metrics: file sizes, token estimates, priority labels, and a health indicator.

```
Loaded Context — haneycli
┏━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━┓
┃ File        ┃   Size ┃ Est Tokens┃ Priority ┃
┡━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━┩
│ summary.md  │ 0.8 KB │       200 │ high     │
│ memory.md   │ 1.2 KB │       300 │ high     │
│ plan.md     │ 2.3 KB │       580 │ high     │
│ README.md   │ 4.7 KB │      1180 │ high     │
├─────────────┼────────┼───────────┼──────────┤
│ Total       │ 9.0 KB │      2260 │          │
└─────────────┴────────┴───────────┴──────────┘

Context Status: Healthy
```

Health thresholds:
- **Healthy** — under 4,000 tokens
- **Moderate** — 4,000–8,000 tokens
- **Large** — over 8,000 tokens (consider `/compact`)

### `/init`

Generates starter project files:

```
✓ Created memory.md
✓ Created summary.md
✓ Created tasks.md
✓ Created plan.md
```

Only creates files that don't already exist. Never overwrites user content.

- `plan.md` → project root
- `memory.md`, `summary.md`, `tasks.md` → `.haney/`

## Token Estimation

Simple character-based estimation: `tokens ≈ characters / 4`. Accuracy is not critical — the purpose is user visibility and context health monitoring, not exact billing.

## Missing Files

Haney never fails due to missing project files. If `plan.md` doesn't exist:

```
Missing Files:
  ⚠ plan.md
  ⚠ summary.md

Detected Files:
  ✓ README.md

Suggestion:
Run /init to generate project files.
```

Project awareness is simply reduced. The LLM receives only the files that exist.

## Design Rationale

**Why auto-discover instead of manual attach?**

Manual attachment (`@file`) exists for ad-hoc needs. But for project-wide context, auto-discovery ensures the model always sees the latest state without the user remembering to attach files.

**Why inject into system prompt instead of user message?**

System prompt injection means the model treats project context as authoritative background knowledge, not as part of the user's question. This leads to better reasoning and fewer "as mentioned in the project context..." disclaimers.

**Why source files are not auto-injected?**

Source files can be massive. Injecting them all would blow context limits. Use `@file` for specific source files when needed. The file listing is available for reference.
