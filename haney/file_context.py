"""File context attachment system for Haney.

Provides FileContextManager that handles @file syntax parsing,
file reading, token estimation, and context preparation for LLM.
"""

from __future__ import annotations

import re
from pathlib import Path
from dataclasses import dataclass, field

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from haney.providers import load_config

# ── Attachment regex ──────────────────────────────────────────────────────────

_ATTACH_RE = re.compile(r"@(\S+)")

# ── Supported file types ──────────────────────────────────────────────────────

TEXT_EXTS = {
    ".txt", ".md", ".rst", ".log", ".csv", ".org",
}
CODE_EXTS = {
    # Python
    ".py", ".pyi", ".pyx", ".pxd",
    # JavaScript / TypeScript
    ".js", ".jsx", ".mjs", ".cjs",
    ".ts", ".tsx", ".mts", ".cts",
    # Web
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
    ".vue", ".svelte", ".astro",
    # JVM
    ".java", ".kt", ".kts", ".scala", ".groovy",
    ".clj", ".cljs", ".cljc", ".edn",
    # C / C++
    ".c", ".h", ".cpp", ".hpp", ".cc", ".cxx", ".hxx",
    # Systems
    ".go", ".rs", ".zig", ".nim",
    ".swift", ".m", ".mm",
    # .NET
    ".cs", ".fs", ".vb", ".csproj", ".fsproj",
    # Ruby / Crystal
    ".rb", ".cr", ".erb",
    # PHP
    ".php", ".phtml",
    # Shell
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".psm1",
    # Functional
    ".hs", ".lhs", ".erl", ".hrl", ".ex", ".exs",
    ".ml", ".mli", ".elm", ".rkt", ".scm",
    # Data / Config / Query
    ".sql", ".graphql", ".gql",
    ".r", ".jl", ".lua", ".dart",
    ".proto", ".thrift", ".tf", ".hcl",
    ".cmake", ".make", ".mk",
    ".dockerfile", "dockerfile",
    ".nix", ".dhall",
    # Documentation / Styles
    ".tex", ".bib", ".typ",
}
CONFIG_EXTS = {
    ".json", ".jsonc", ".yaml", ".yml", ".toml", ".ini",
    ".cfg", ".conf", ".env", ".properties",
    ".xml", ".plist",
    ".lock",
}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"}

ALL_SUPPORTED = TEXT_EXTS | CODE_EXTS | CONFIG_EXTS | IMAGE_EXTS

DEFAULT_MAX_TOKENS = 10000


@dataclass
class AttachedFile:
    """A successfully attached file."""

    name: str
    path: Path
    content: str  # text content or image metadata
    tokens: int
    size_bytes: int
    is_image: bool = False


class FileContextManager:
    """Manages @file attachments for the current conversation.

    Parses @file references from user input, reads files,
    estimates tokens, and prepares context for LLM injection.
    Attachments persist for the session and are cleared on /clear.
    """

    def __init__(self, cwd: Path | None = None) -> None:
        """Initialise the attachment manager.

        Args:
            cwd: Working directory. Defaults to current.
        """
        self.cwd = (cwd or Path.cwd()).resolve()
        self._attachments: dict[str, AttachedFile] = {}  # keyed by name

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def max_tokens(self) -> int | None:
        """Return the configurable max attachment tokens, or None for unlimited."""
        config = load_config(self.cwd)
        return config.get("max_attachment_tokens", DEFAULT_MAX_TOKENS)

    @property
    def attached_files(self) -> list[AttachedFile]:
        """Return all attached files in order of attachment."""
        return list(self._attachments.values())

    @property
    def total_tokens(self) -> int:
        """Total estimated tokens across all attachments."""
        return sum(f.tokens for f in self._attachments.values())

    @property
    def empty(self) -> bool:
        """True if no files are attached."""
        return len(self._attachments) == 0

    # ── Parsing ───────────────────────────────────────────────────────────

    def parse_attachments(self, text: str) -> list[str]:
        """Extract @file references from user input.

        Handles relative paths, absolute paths, and nested paths.
        Skips @ mentions that aren't valid file paths (e.g., @username).

        Args:
            text: Raw user input possibly containing @file references.

        Returns:
            List of filenames (including relative paths like 'src/main.py').
        """
        raw = _ATTACH_RE.findall(text)
        # Filter out things that look like mentions, not files (@username)
        # A file reference must contain a dot or a path separator
        return [r for r in raw if "." in r or "/" in r]

    def strip_attachments(self, text: str) -> str:
        """Remove @file references from user input.

        Args:
            text: Raw user input.

        Returns:
            Cleaned text with @file references removed and whitespace normalised.
        """
        cleaned = _ATTACH_RE.sub("", text)
        # Collapse multiple spaces
        import re as _re
        return _re.sub(r"\s+", " ", cleaned).strip()

    # ── Attach / detach ───────────────────────────────────────────────────

    def attach_files(
        self, names: list[str], console: Console | None = None
    ) -> list[str]:
        """Read and attach files by name.

        For each @file reference, resolves the path relative to cwd,
        reads the content (or image metadata), and stores it.
        Never raises — missing files are reported and skipped.

        Args:
            names: List of filenames from @file references.
            console: Optional console for status output.

        Returns:
            List of filenames that could NOT be attached (errors).
        """
        errors: list[str] = []

        for name in names:
            original_name = name  # preserve for display

            # Skip if already attached
            if name in self._attachments:
                continue

            path = (self.cwd / name).resolve()

            # Security: don't allow escaping cwd
            try:
                path.relative_to(self.cwd)
            except ValueError:
                errors.append(f"{name} (outside project)")
                if console:
                    console.print(f"  [yellow]⚠[/yellow] {name} [dim](outside project — skipped)[/dim]")
                continue

            fuzzy = False
            if not path.is_file():
                # Try fuzzy find — search recursively for the filename
                found = _find_file(self.cwd, name)
                if found:
                    path = found
                    fuzzy = True
                    try:
                        name = str(path.relative_to(self.cwd))
                    except ValueError:
                        pass
                else:
                    errors.append(f"{name} (not found)")
                    if console:
                        rel = str(path.relative_to(self.cwd)) if _is_under(path, self.cwd) else str(path)
                        console.print(f"  [yellow]⚠[/yellow] {name} [dim](not found — looked at {rel})[/dim]")
                    continue

            ext = path.suffix.lower()
            if ext not in ALL_SUPPORTED:
                errors.append(f"{name} (unsupported type: {ext})")
                if console:
                    console.print(f"  [yellow]⚠[/yellow] {name} [dim](unsupported type)[/dim]")
                continue

            size = path.stat().st_size

            # ── Image: metadata only ──────────────────────────
            if ext in IMAGE_EXTS:
                meta = _read_image_meta(path)
                if meta is None:
                    errors.append(f"{name} (could not read)")
                    if console:
                        console.print(f"  [yellow]⚠[/yellow] {name} [dim](could not read)[/dim]")
                    continue

                self._attachments[name] = AttachedFile(
                    name=name,
                    path=path,
                    content=meta,
                    tokens=self._estimate(meta),
                    size_bytes=size,
                    is_image=True,
                )
                if console:
                    console.print(f"  [green]✓[/green] {name} [dim](image, metadata only)[/dim]")
                continue

            # ── Text / code / config ──────────────────────────
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                errors.append(f"{name} (could not read)")
                if console:
                    console.print(f"  [yellow]⚠[/yellow] {name} [dim](could not read)[/dim]")
                continue

            tokens = self._estimate(content)
            self._attachments[name] = AttachedFile(
                name=name,
                path=path,
                content=content,
                tokens=tokens,
                size_bytes=size,
            )

            if console:
                kb = size / 1024
                fuzzy_note = f" [dim](→ {name})[/dim]" if fuzzy else ""
                console.print(
                    f"  [green]✓[/green] {original_name}{fuzzy_note} "
                    f"[dim]({kb:.1f} KB, ~{tokens} tokens)[/dim]"
                )

        return errors

    def clear(self) -> None:
        """Remove all attachments."""
        self._attachments.clear()

    # ── Token estimation ───────────────────────────────────────────────────

    def _estimate(self, content: str) -> int:
        """Simple token estimate: characters ÷ 4."""
        return max(1, len(content) // 4)

    # ── Context for LLM ────────────────────────────────────────────────────

    def build_context(self) -> str:
        """Build the attachment context preamble for LLM injection.

        Respects max_tokens — truncates with a warning if exceeded.

        Returns:
            Formatted string of file contents, or empty string.
        """
        if not self._attachments:
            return ""

        parts = ["## Attached Files\n"]
        total = 0
        truncated = False

        for f in self._attachments.values():
            if f.is_image:
                parts.append(
                    f"### {f.name} (image)\n\n{f.content}\n\n"
                )
                continue

            lang = f.path.suffix.lstrip(".")
            parts.append(f"### {f.name}\n```{lang}\n")

            # Truncation only when max_tokens is set
            if self.max_tokens is not None:
                remaining = self.max_tokens - total
                if remaining <= 0:
                    truncated = True
                    break

                content = f.content
                content_tokens = self._estimate(content)
                if content_tokens > remaining:
                    content = content[: remaining * 4]
                    truncated = True
            else:
                content = f.content

            parts.append(content)
            if not content.endswith("\n"):
                parts.append("\n")
            parts.append("```\n\n")
            total += self._estimate(content)

        if truncated:
            parts.append(
                f"*Attachment context exceeded {self.max_tokens} token limit. "
                "Some content was omitted.*\n"
            )

        return "".join(parts)

    # ── Display ────────────────────────────────────────────────────────────

    def display_summary(self, console: Console) -> None:
        """Render an attachment summary panel in Rich UI.

        Args:
            console: Rich Console for output.
        """
        if not self._attachments:
            console.print("[dim]No files attached.[/dim]")
            return

        table = Table(
            title="Attached Files",
            border_style="green",
            title_justify="left",
        )
        table.add_column("File", style="bold cyan", no_wrap=True)
        table.add_column("Size", style="dim", justify="right")
        table.add_column("Est. Tokens", style="dim", justify="right")

        for f in self._attachments.values():
            kb = f.size_bytes / 1024
            label = f"{f.name} 🖼" if f.is_image else f.name
            table.add_row(label, f"{kb:.1f} KB", str(f.tokens))

        table.add_section()
        table.add_row(
            "[bold]Total[/bold]",
            "",
            f"[bold]{self.total_tokens}[/bold]",
        )

        console.print(table)


# ── Image helpers ─────────────────────────────────────────────────────────────

def _find_file(cwd: Path, name: str) -> Path | None:
    """Recursively search for a file by name within cwd.

    Limits to 3 levels deep to avoid scanning huge directories.
    Skips hidden directories (.git, .venv, node_modules, etc.).

    Args:
        cwd: Root directory to search from.
        name: Filename to find (e.g., 'sum.py').

    Returns:
        Resolved Path if exactly one match is found, None otherwise.
    """
    # Skip if the name contains path separators — it's an explicit path
    if "/" in name or "\\" in name:
        return None

    skip_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"}
    matches: list[Path] = []

    try:
        for depth, path in enumerate(cwd.rglob(name), 1):
            if depth > 500:  # safety limit
                break
            # Skip hidden/noise directories
            parts = set(path.relative_to(cwd).parts)
            if parts & skip_dirs:
                continue
            if len(path.relative_to(cwd).parts) > 4:  # max 3 levels deep
                continue
            matches.append(path)
    except OSError:
        return None

    if len(matches) == 1:
        return matches[0]
    return None


def _is_under(path: Path, parent: Path) -> bool:
    """Check if path is under parent directory."""
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
    """Read image metadata using Pillow.

    Args:
        path: Path to the image file.

    Returns:
        A metadata description string, or None on failure.
    """
    try:
        from PIL import Image
    except ImportError:
        return None

    try:
        with Image.open(path) as img:
            w, h = img.size
            fmt = img.format or path.suffix.upper().lstrip(".")
            return f"**Format:** {fmt}  \n**Dimensions:** {w}×{h} pixels  \n"
    except Exception:
        return None
