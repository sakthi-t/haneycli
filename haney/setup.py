"""First-run setup wizard for Haney.

Creates the .haney directory and default helper files when
Haney runs for the first time in a project.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from haney.config import HANEY_DIR

SYSTEM_MD_CONTENT = """You are Haney.

A helpful terminal-based AI coding assistant.

Core Responsibilities:

* Help users write code.
* Help users debug code.
* Explain technical concepts.
* Prefer maintainable solutions.
* Be concise and helpful.

Tools:

You have access to file and shell tools. When a user asks you to
do something that requires reading, writing, editing, or deleting
files — or running a shell command — CALL THE TOOL DIRECTLY.

Do NOT say "I'll do that" and then wait. Execute the tool immediately.
Do NOT ask for permission. The system handles confirmation prompts.

Project Awareness:

* Read plan.md if available.
* Read memory.md if available.
* Read summary.md if available.

Internet Usage:

* Search for current information when needed.
* Do not rely solely on training knowledge.

Safety:

* Never execute dangerous operations without confirmation.

Identity:

You are Haney, an apartment cat helping developers build useful things.
"""

HELP_MD_CONTENT = """# Haney Commands

## Available Commands

| Command            | Description                       |
|--------------------|-----------------------------------|
| `/help`            | Display this help message         |
| `/version`         | Show Haney version                |
| `/clear`           | Clear the terminal screen         |
| `/exit`            | Exit Haney gracefully             |
| `/login <provider>`| Connect an LLM provider or Exa    |
| `/logout [provider]`| Disconnect from a provider       |
| `/models [provider]`| List all available models         |
| `/model [name]`    | Show or set the active model      |
| `/provider`        | Show current provider status      |
| `/project`         | Show project status & files       |
| `/reload`          | Re-scan project files             |
| `/context`         | Show loaded context details       |
| `/init`            | Generate starter project files    |
| `/trash`           | Show files in trash               |
| `/restore <file>`  | Restore a file from trash         |

## Attaching Files

Use `@filename` in any chat message to attach files.
- `@main.py` — attach a source file
- `@src/app.py` — attach nested paths
- `/attachments` — view currently attached files
- `/clear` — clear screen, history, and attachments

## Getting Started

1. Connect an LLM: `/login openai`
2. Pick a model: `/model gpt-4o`
3. (Optional) Enable search: `/login exa`
4. Set up project awareness: `/init`
5. Start chatting — just type your message!

## Supported Providers

LLM: openai, anthropic, deepseek, gemini, openrouter, groq
Search: exa

## Configuration

API keys are stored in `.haney/config.json`.
You can also set environment variables:
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.
- `EXA_API_KEY` (fallback if not set via `/login exa`)

Use `/help` to see this information at any time.
"""

MEMORY_MD_CONTENT = """# Project Memory

This file stores long-term project memory for Haney.

Add notes, preferences, conventions, and other persistent context here.
"""

SESSIONS_MD_CONTENT = """# Sessions

Session history and summaries will be recorded here.
"""


def is_setup_complete(cwd: Path | None = None) -> bool:
    """Check if the .haney directory exists in the working directory.

    Args:
        cwd: Working directory to check. Defaults to current directory.

    Returns:
        True if .haney directory exists, False otherwise.
    """
    target = (cwd or Path.cwd()) / HANEY_DIR
    return target.is_dir()


def run_setup(console: Console, cwd: Path | None = None) -> None:
    """Run the first-run setup wizard.

    Prompts the user to create the .haney directory and default files.
    If the user declines, Haney still starts without project files.

    Args:
        console: Rich Console instance for output.
        cwd: Working directory for setup. Defaults to current directory.
    """
    target = (cwd or Path.cwd()) / HANEY_DIR

    welcome = Panel(
        "Welcome to Haney.\n\nCreate project files?",
        border_style="green",
        title="Setup",
        title_align="left",
    )
    console.print(welcome)

    confirmed = Confirm.ask("", default=True)

    if not confirmed:
        console.print("[dim]Skipping project file creation.[/dim]")
        return

    _create_project_files(target, console)


def _create_project_files(haney_dir: Path, console: Console) -> None:
    """Create the .haney directory and all default helper files.

    Args:
        haney_dir: Path to the .haney directory.
        console: Rich Console instance for output.
    """
    import json
    from haney.config_bootstrap import CONFIG_SCHEMA

    try:
        haney_dir.mkdir(parents=True, exist_ok=True)

        file_contents: dict[str, str] = {
            "system.md": SYSTEM_MD_CONTENT,
            "memory.md": MEMORY_MD_CONTENT,
            "sessions.md": SESSIONS_MD_CONTENT,
            "help.md": HELP_MD_CONTENT,
        }

        for filename, content in file_contents.items():
            filepath = haney_dir / filename
            filepath.write_text(content, encoding="utf-8")

        # Create config.json from the master schema
        config_path = haney_dir / "config.json"
        if not config_path.exists():
            config_path.write_text(
                json.dumps(CONFIG_SCHEMA, indent=2), encoding="utf-8"
            )

        summary = Panel(
            "\n".join(f"  ✓ {f}" for f in sorted(list(file_contents) + ["config.json"])),
            border_style="green",
            title="Created Files",
            title_align="left",
        )
        console.print(summary)
        console.print(f"\n[dim]Project files created in {haney_dir}/[/dim]")

    except OSError as exc:
        console.print(f"[red]Error creating project files: {exc}[/red]")
