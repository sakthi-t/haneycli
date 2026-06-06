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
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico", ".tiff", ".tif"}

# ── Binary / rich formats (metadata only) ────────────────────────────────────
BINARY_META_EXTS: set[str] = {
    ".pdf",
    ".docx", ".doc",
    ".xlsx", ".xls",
    ".pptx", ".ppt",
    ".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a",
    ".mp4", ".avi", ".mov", ".mkv", ".webm",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".epub", ".mobi",
}

ALL_SUPPORTED = TEXT_EXTS | CODE_EXTS | CONFIG_EXTS | IMAGE_EXTS | BINARY_META_EXTS

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
                    kb = size / 1024
                    console.print(f"  [green]✓[/green] {name} [dim](🖼 image, {kb:.1f} KB)[/dim]")
                continue

            # ── Binary / rich format: metadata only ─────────
            if ext in BINARY_META_EXTS:
                meta = _read_binary_meta(path, ext)
                self._attachments[name] = AttachedFile(
                    name=name,
                    path=path,
                    content=meta,
                    tokens=self._estimate(meta),
                    size_bytes=size,
                )
                if console:
                    kb = size / 1024
                    fmt_label = ext.upper().lstrip(".")
                    console.print(f"  [green]✓[/green] {name} [dim]({fmt_label}, metadata only, {kb:.1f} KB)[/dim]")
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

            ext = f.path.suffix.lower()
            if ext in BINARY_META_EXTS:
                # Binary/rich format: show metadata as plain text
                parts.append(f"### {f.name} (binary)\n\n{f.content}\n\n")
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

    def compact_status(self) -> str:
        """Return a compact one-line status for the composer bar.

        Returns:
            Empty string if no attachments, otherwise:
            '📎 ×3 (45KB, ~1.2k tokens)'
        """
        if self.empty:
            return ""
        total_kb = sum(f.size_bytes for f in self._attachments.values()) / 1024
        if total_kb >= 1024:
            size_str = f"{total_kb / 1024:.1f}MB"
        else:
            size_str = f"{total_kb:.0f}KB"
        token_str = f"{self.total_tokens / 1000:.1f}k" if self.total_tokens >= 1000 else str(self.total_tokens)
        return f"📎 ×{len(self._attachments)} ({size_str}, ~{token_str})"

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
            if f.is_image:
                label = f"{f.name} 🖼"
            elif f.path.suffix.lower() in BINARY_META_EXTS:
                fmt = f.path.suffix.upper().lstrip(".")
                label = f"{f.name} 📦 {fmt}"
            else:
                label = f.name
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


def _read_image_meta(path: Path) -> str | None:
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


def _read_binary_meta(path: Path, ext: str) -> str:
    """Generate metadata for binary / rich format files.

    Attempts text extraction for PDFs (pypdf) and DOCX (python-docx).
    Falls back to file-type-and-size metadata if extraction fails
    or the format isn't supported for extraction.

    Args:
        path: Path to the file.
        ext: Lowercased file extension.

    Returns:
        Formatted metadata string (possibly with extracted text).
    """
    size_bytes = path.stat().st_size
    if size_bytes >= 1_048_576:
        size_str = f"{size_bytes / 1_048_576:.1f} MB"
    elif size_bytes >= 1024:
        size_str = f"{size_bytes / 1024:.1f} KB"
    else:
        size_str = f"{size_bytes} bytes"

    fmt = ext.upper().lstrip(".")

    # ── PDF: try text extraction with pypdf ──────────────────
    if ext == ".pdf":
        text = _try_extract_pdf(path)
        if text is not None:
            return (
                f"**File type:** PDF\n"
                f"**Size:** {size_str}\n"
                f"**Pages extracted:** see content below\n\n"
                f"{text}\n"
            )

    # ── DOCX: try text extraction with python-docx ──────────
    if ext == ".docx":
        text = _try_extract_docx(path)
        if text is not None:
            return (
                f"**File type:** DOCX\n"
                f"**Size:** {size_str}\n"
                f"**Content extracted:** see below\n\n"
                f"{text}\n"
            )

    # ── Fallback: metadata only ─────────────────────────────
    return (
        f"**File type:** {fmt}\n"
        f"**Size:** {size_str}\n"
        f"**Note:** Binary file — content preview not available.\n"
    )


def _try_extract_pdf(path: Path) -> str | None:
    """Try to extract text from a PDF file using pypdf.

    Returns concatenated text from all pages, or None on failure.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        return None

    try:
        reader = PdfReader(str(path))
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text and text.strip():
                pages.append(f"--- Page {i + 1} ---\n{text.strip()}")
        if not pages:
            return None
        return "\n\n".join(pages)
    except Exception:
        return None


def _try_extract_docx(path: Path) -> str | None:
    """Try to extract text from a DOCX file using python-docx.

    Returns concatenated paragraph text, or None on failure.
    """
    try:
        from docx import Document
    except ImportError:
        return None

    try:
        doc = Document(str(path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        if not paragraphs:
            return None
        return "\n\n".join(paragraphs)
    except Exception:
        return None
