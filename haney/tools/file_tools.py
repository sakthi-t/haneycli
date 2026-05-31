"""File operation tools for Haney.

Implements read, write, edit, rename, delete (trash), and list-directory
operations — all constrained to the project root.
"""

from __future__ import annotations

import shutil
import difflib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FileToolResult:
    """Result of a file tool operation."""

    success: bool
    message: str
    path: str = ""
    content_preview: str = ""


# ── Safety ────────────────────────────────────────────────────────────────────

def _resolve_safe(root: Path, rel_path: str) -> Path:
    """Resolve a relative path and ensure it stays within the project root.

    Args:
        root: Project root directory.
        rel_path: Relative path from user/model.

    Returns:
        Resolved absolute Path.

    Raises:
        ValueError: If the path escapes the project root.
    """
    target = (root / rel_path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise ValueError(f"Path escapes project root: {rel_path}")
    return target


# ── Read ──────────────────────────────────────────────────────────────────────

def read_file(root: Path, path: str, max_lines: int = 500) -> FileToolResult:
    """Read a file's contents.

    No confirmation required.

    Args:
        root: Project root directory.
        path: Relative path to the file.
        max_lines: Maximum lines to return.

    Returns:
        FileToolResult with content or error.
    """
    try:
        target = _resolve_safe(root, path)
    except ValueError as exc:
        return FileToolResult(success=False, message=str(exc))

    if not target.is_file():
        return FileToolResult(
            success=False, message=f"File not found: {path}"
        )

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return FileToolResult(
            success=False, message=f"Cannot read {path}: {exc}"
        )

    lines = content.splitlines()
    total = len(lines)
    if total > max_lines:
        shown = "\n".join(lines[:max_lines])
        preview = (
            f"{shown}\n\n… [{total - max_lines} more lines — "
            f"{total} total]"
        )
    else:
        preview = content

    return FileToolResult(
        success=True,
        message=f"Read {path} ({total} lines)",
        path=str(target),
        content_preview=preview,
    )


# ── Write ─────────────────────────────────────────────────────────────────────

def write_file(root: Path, path: str, content: str) -> FileToolResult:
    """Create or overwrite a file.

    Requires confirmation before execution.

    Args:
        root: Project root directory.
        path: Relative path to the file.
        content: Content to write.

    Returns:
        FileToolResult.
    """
    try:
        target = _resolve_safe(root, path)
    except ValueError as exc:
        return FileToolResult(success=False, message=str(exc))

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except OSError as exc:
        return FileToolResult(
            success=False, message=f"Cannot write {path}: {exc}"
        )

    lines = content.count("\n") + 1
    return FileToolResult(
        success=True,
        message=f"Wrote {path} ({lines} lines, {len(content)} chars)",
        path=str(target),
    )


# ── Edit ──────────────────────────────────────────────────────────────────────

def edit_file(
    root: Path, path: str, old_text: str, new_text: str
) -> FileToolResult:
    """Replace text in a file using exact match.

    Requires confirmation before execution.

    Args:
        root: Project root directory.
        path: Relative path to the file.
        old_text: Exact text to find and replace.
        new_text: Replacement text.

    Returns:
        FileToolResult with diff summary.
    """
    try:
        target = _resolve_safe(root, path)
    except ValueError as exc:
        return FileToolResult(success=False, message=str(exc))

    if not target.is_file():
        return FileToolResult(
            success=False, message=f"File not found: {path}"
        )

    try:
        original = target.read_text(encoding="utf-8")
    except OSError as exc:
        return FileToolResult(
            success=False, message=f"Cannot read {path}: {exc}"
        )

    if old_text not in original:
        return FileToolResult(
            success=False,
            message=f"Text not found in {path}. No changes made.",
        )

    modified = original.replace(old_text, new_text, 1)
    try:
        target.write_text(modified, encoding="utf-8")
    except OSError as exc:
        return FileToolResult(
            success=False, message=f"Cannot write {path}: {exc}"
        )

    # Build diff summary
    diff_lines = list(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            modified.splitlines(keepends=True),
            fromfile=path,
            tofile=path,
        )
    )
    changed = sum(1 for l in diff_lines if l.startswith(("+", "-")) and not l.startswith(("+++", "---")))

    return FileToolResult(
        success=True,
        message=f"Edited {path} ({changed} lines changed)",
        path=str(target),
        content_preview="".join(diff_lines[:30]),
    )


# ── Rename ────────────────────────────────────────────────────────────────────

def rename_file(root: Path, old_path: str, new_path: str) -> FileToolResult:
    """Rename or move a file within the project root.

    Requires confirmation before execution.

    Args:
        root: Project root directory.
        old_path: Current relative path.
        new_path: New relative path.

    Returns:
        FileToolResult.
    """
    try:
        src = _resolve_safe(root, old_path)
        dst = _resolve_safe(root, new_path)
    except ValueError as exc:
        return FileToolResult(success=False, message=str(exc))

    if not src.is_file():
        return FileToolResult(
            success=False, message=f"Source not found: {old_path}"
        )

    if dst.exists():
        return FileToolResult(
            success=False, message=f"Destination already exists: {new_path}"
        )

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    except OSError as exc:
        return FileToolResult(
            success=False, message=f"Cannot rename: {exc}"
        )

    return FileToolResult(
        success=True,
        message=f"Renamed {old_path} → {new_path}",
        path=str(dst),
    )


# ── Delete (trash) ────────────────────────────────────────────────────────────

def delete_file(root: Path, path: str) -> FileToolResult:
    """Move a file to .haney/trash/ instead of permanent deletion.

    Requires confirmation before execution.

    Args:
        root: Project root directory.
        path: Relative path to the file.

    Returns:
        FileToolResult.
    """
    try:
        src = _resolve_safe(root, path)
    except ValueError as exc:
        return FileToolResult(success=False, message=str(exc))

    if not src.is_file():
        return FileToolResult(
            success=False, message=f"File not found: {path}"
        )

    trash_dir = root / ".haney" / "trash"
    trash_dir.mkdir(parents=True, exist_ok=True)

    # Avoid name collisions in trash
    dest_name = src.name
    dest = trash_dir / dest_name
    counter = 1
    while dest.exists():
        stem = src.stem
        dest = trash_dir / f"{stem}_{counter}{src.suffix}"
        counter += 1

    try:
        shutil.move(str(src), str(dest))
    except OSError as exc:
        return FileToolResult(
            success=False, message=f"Cannot delete: {exc}"
        )

    return FileToolResult(
        success=True,
        message=f"Moved {path} to trash ({dest.name})",
        path=str(dest),
    )


# ── Restore ───────────────────────────────────────────────────────────────────

def restore_file(root: Path, filename: str) -> FileToolResult:
    """Restore a file from .haney/trash/ back to the project root.

    Args:
        root: Project root directory.
        filename: Name of the file in trash.

    Returns:
        FileToolResult.
    """
    trash_dir = root / ".haney" / "trash"
    src = trash_dir / filename

    if not src.is_file():
        return FileToolResult(
            success=False,
            message=f"'{filename}' not found in trash.",
        )

    dest = root / filename
    if dest.exists():
        return FileToolResult(
            success=False,
            message=f"'{filename}' already exists in project root.",
        )

    try:
        shutil.move(str(src), str(dest))
    except OSError as exc:
        return FileToolResult(
            success=False, message=f"Cannot restore: {exc}"
        )

    return FileToolResult(
        success=True,
        message=f"Restored {filename} from trash",
        path=str(dest),
    )


# ── List Directory ────────────────────────────────────────────────────────────

def list_directory(
    root: Path, path: str = ".", max_entries: int = 100
) -> FileToolResult:
    """List files and directories.

    No confirmation required.

    Args:
        root: Project root directory.
        path: Relative directory path.
        max_entries: Maximum entries to return.

    Returns:
        FileToolResult with listing.
    """
    try:
        target = _resolve_safe(root, path)
    except ValueError as exc:
        return FileToolResult(success=False, message=str(exc))

    if not target.is_dir():
        return FileToolResult(
            success=False, message=f"Not a directory: {path}"
        )

    try:
        entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError as exc:
        return FileToolResult(
            success=False, message=f"Cannot list {path}: {exc}"
        )

    lines = []
    for i, entry in enumerate(entries):
        if i >= max_entries:
            lines.append(f"… and {len(entries) - max_entries} more entries")
            break
        icon = "📁" if entry.is_dir() else "📄"
        try:
            size = entry.stat().st_size
        except OSError:
            size = 0
        kb = size / 1024
        name = entry.name
        if entry.is_dir():
            name += "/"
        lines.append(f"{icon} {name}  ({kb:.1f} KB)")

    return FileToolResult(
        success=True,
        message=f"Listed {path} ({len(entries)} entries)",
        content_preview="\n".join(lines),
    )


# ── Trash listing ─────────────────────────────────────────────────────────────

def list_trash(root: Path) -> FileToolResult:
    """List files in .haney/trash/.

    Args:
        root: Project root directory.

    Returns:
        FileToolResult with trash listing.
    """
    trash_dir = root / ".haney" / "trash"
    if not trash_dir.is_dir():
        return FileToolResult(
            success=True,
            message="Trash is empty.",
            content_preview="No files in trash.",
        )

    try:
        entries = sorted(trash_dir.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return FileToolResult(
            success=False, message="Cannot read trash directory."
        )

    if not entries:
        return FileToolResult(
            success=True,
            message="Trash is empty.",
            content_preview="No files in trash.",
        )

    lines = [f"📁 .haney/trash/  ({len(entries)} files)\n"]
    for entry in entries:
        try:
            size = entry.stat().st_size
        except OSError:
            size = 0
        kb = size / 1024
        lines.append(f"  📄 {entry.name}  ({kb:.1f} KB)")

    return FileToolResult(
        success=True,
        message=f"{len(entries)} file(s) in trash",
        content_preview="\n".join(lines),
    )
