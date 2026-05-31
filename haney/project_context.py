"""Project awareness for Haney.

Provides ProjectContextManager that discovers, loads, caches,
and serves project files as context for the LLM.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from dataclasses import dataclass, field

from haney.config import HANEY_DIR


# ── File discovery ────────────────────────────────────────────────────────────

# Root-level files (user-owned, committed to git)
ROOT_FILES = ["plan.md", "README.md"]

# .haney/ files (Haney-managed, not committed)
HANEY_FILES = ["summary.md", "memory.md", "tasks.md"]

HIGH_PRIORITY = HANEY_FILES + ROOT_FILES
MEDIUM_PRIORITY = ["architecture.md", "requirements.md"]
SOURCE_GLOBS = ["*.py", "*.js", "*.ts", "*.tsx", "*.json", "*.yaml", "*.yml"]

# Priority order for context loading
PRIORITY_ORDER = [
    "summary.md", "memory.md", "plan.md", "README.md",
    "architecture.md", "tasks.md",
]


@dataclass
class LoadedFile:
    """A discovered and loaded project file."""

    path: Path
    name: str
    size_bytes: int
    content: str
    priority: str  # "high", "medium", "source"
    loaded_at: float = field(default_factory=time.monotonic)


class ProjectContextManager:
    """Discovers, loads, and caches project-awareness files.

    Automatically scans the project root for plan.md, memory.md,
    summary.md, README.md, and source files. Provides context
    injection for LLM messages.
    """

    def __init__(self, cwd: Path | None = None) -> None:
        """Initialise the context manager and run initial discovery.

        Args:
            cwd: Project root directory. Defaults to current directory.
        """
        self.cwd = (cwd or Path.cwd()).resolve()
        self.project_name = self.cwd.name
        self._files: dict[str, LoadedFile] = {}
        self._last_reload: float = 0.0
        self.reload()

    # ── Discovery ─────────────────────────────────────────────────────────

    def _discover_files(self) -> dict[str, tuple[Path, str]]:
        """Scan .haney/ and project root for awareness files.

        Returns:
            Dict of filename → (path, priority).
        """
        found: dict[str, tuple[Path, str]] = {}
        haney_dir = self.cwd / HANEY_DIR

        # .haney/ files (Haney-managed)
        for name in HANEY_FILES:
            p = haney_dir / name
            if p.is_file():
                found[name] = (p, "high")

        # Root-level files (user-owned)
        for name in ROOT_FILES:
            p = self.cwd / name
            if p.is_file():
                found[name] = (p, "high")

        # Medium-priority files (root only)
        for name in MEDIUM_PRIORITY:
            p = self.cwd / name
            if p.is_file():
                found[name] = (p, "medium")

        # Source files (one level deep)
        for pattern in SOURCE_GLOBS:
            for p in sorted(self.cwd.glob(pattern)):
                if p.is_file() and p.name not in found:
                    found[p.name] = (p, "source")

        return found

    def reload(self) -> None:
        """Re-scan and reload all project files. Never raises."""
        self._last_reload = time.monotonic()
        discovered = self._discover_files()

        loaded: dict[str, LoadedFile] = {}
        for name, (path, priority) in discovered.items():
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                loaded[name] = LoadedFile(
                    path=path,
                    name=name,
                    size_bytes=path.stat().st_size,
                    content=content,
                    priority=priority,
                )
            except OSError:
                # File vanished or is unreadable — skip it
                continue

        self._files = loaded

    # ── Accessors ──────────────────────────────────────────────────────────

    @property
    def loaded_files(self) -> list[LoadedFile]:
        """Return all loaded files in priority order."""
        def _key(item: tuple[str, LoadedFile]) -> tuple[int, str]:
            name, f = item
            try:
                idx = PRIORITY_ORDER.index(name)
            except ValueError:
                idx = 99
            return (idx, name)

        return [v for _, v in sorted(self._files.items(), key=_key)]

    @property
    def high_priority_files(self) -> list[LoadedFile]:
        """Return high-priority awareness files."""
        return [f for f in self.loaded_files if f.priority == "high"]

    @property
    def missing_awareness_files(self) -> list[str]:
        """Return awareness file names that were not found."""
        loaded_names = {f.name for f in self._files.values()}
        return [n for n in HIGH_PRIORITY if n not in loaded_names]

    @property
    def has_any_awareness(self) -> bool:
        """Check if any awareness files were found."""
        return any(f.priority == "high" for f in self._files.values())

    @property
    def last_reload_seconds(self) -> float:
        """Seconds since last reload."""
        return time.monotonic() - self._last_reload

    def get_file(self, name: str) -> LoadedFile | None:
        """Get a specific loaded file by name."""
        return self._files.get(name)

    # ── Token estimation ───────────────────────────────────────────────────

    def estimate_tokens(self, content: str) -> int:
        """Simple token estimate: characters ÷ 4.

        Args:
            content: Text to estimate.

        Returns:
            Approximate token count.
        """
        return max(1, len(content) // 4)

    @property
    def total_tokens(self) -> int:
        """Estimated total tokens across all loaded files."""
        return sum(self.estimate_tokens(f.content) for f in self._files.values())

    # ── Context for LLM ────────────────────────────────────────────────────

    def build_context_preamble(self) -> str:
        """Build a context preamble for injection into the system prompt.

        Returns:
            Formatted string with project file contents, or empty string.
        """
        awareness_files = [f for f in self.loaded_files if f.priority in ("high", "medium")]
        if not awareness_files:
            return ""

        parts = ["## Project Context\n"]
        parts.append(f"**Project:** {self.project_name}\n")

        for f in awareness_files:
            tokens = self.estimate_tokens(f.content)
            size_kb = f.size_bytes / 1024
            parts.append(
                f"### {f.name}  ({size_kb:.1f} KB, ~{tokens} tokens)\n\n"
                f"{f.content}\n"
            )

        return "\n".join(parts)

    # ── /init file templates ───────────────────────────────────────────────

    @staticmethod
    def _template_plan_md(project_name: str) -> str:
        return (
            f"# {project_name} — Project Plan\n\n"
            "## Overview\n\n"
            "<!-- Describe what this project does. -->\n\n"
            "## Goals\n\n"
            "<!-- List project goals. -->\n\n"
            "## Architecture\n\n"
            "<!-- High-level architecture notes. -->\n\n"
            "## Tasks\n\n"
            "<!-- Current task list. -->\n"
        )

    @staticmethod
    def _template_memory_md() -> str:
        return (
            "# Project Memory\n\n"
            "This file stores long-term project memory.\n\n"
            "Add notes, preferences, conventions, and "
            "other persistent context here.\n"
        )

    @staticmethod
    def _template_summary_md() -> str:
        return (
            "# Project Summary\n\n"
            "<!-- A concise summary of the project's current state. -->\n"
        )

    @staticmethod
    def _template_tasks_md() -> str:
        return (
            "# Tasks\n\n"
            "## Todo\n\n"
            "<!-- Pending tasks. -->\n\n"
            "## In Progress\n\n"
            "<!-- Tasks being worked on. -->\n\n"
            "## Done\n\n"
            "<!-- Completed tasks. -->\n"
        )

    def init_files(self) -> list[str]:
        """Create starter project-awareness files.

        Haney-managed files (memory.md, summary.md, tasks.md)
        are created in .haney/. User-owned files (plan.md) are
        created at the project root.

        Only creates files that do not already exist.

        Returns:
            List of filenames that were created.
        """
        haney_dir = self.cwd / HANEY_DIR
        haney_dir.mkdir(parents=True, exist_ok=True)

        # .haney/ files
        haney_templates: dict[str, str] = {
            "memory.md": self._template_memory_md(),
            "summary.md": self._template_summary_md(),
            "tasks.md": self._template_tasks_md(),
        }

        # Root files
        root_templates: dict[str, str] = {
            "plan.md": self._template_plan_md(self.project_name),
        }

        created: list[str] = []

        for name, content in haney_templates.items():
            dest = haney_dir / name
            if not dest.exists():
                try:
                    dest.write_text(content, encoding="utf-8")
                    created.append(name)
                except OSError:
                    pass

        for name, content in root_templates.items():
            dest = self.cwd / name
            if not dest.exists():
                try:
                    dest.write_text(content, encoding="utf-8")
                    created.append(name)
                except OSError:
                    pass

        return created
