"""Workspace filesystem accessor — models DeepSeek Harness ``dsh-fs``.

A single ``LocalFilesystem`` instance confines every operation to a workspace
root (path traversal is rejected) and honours an optional ``read_only`` flag so
the runtime can hand an agent a read-only or read-write view without a separate
tool catalog.  The tools in ``tools/fs_tool.py`` wrap these operations.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path

MAX_GREP_MATCHES = 250


class FilesystemError(ValueError):
    """Raised for path escapes, missing files, and read-only violations."""


@dataclass(frozen=True, slots=True)
class GrepMatch:
    path: str
    line_number: int
    text: str

    def as_dict(self) -> dict[str, object]:
        return {"path": self.path, "line_number": self.line_number, "text": self.text}


class LocalFilesystem:
    """Read/write/edit/glob/grep scoped to one workspace root."""

    def __init__(self, root: str | Path, read_only: bool = False) -> None:
        self.root = Path(root).resolve()
        self.read_only = read_only

    # ── path safety ────────────────────────────────────────────────────────

    def _resolve(self, path: str | None) -> Path:
        candidate = (self.root / path).resolve() if path else self.root
        if candidate != self.root and not candidate.is_relative_to(self.root):
            raise FilesystemError(f"path escapes workspace root: {path}")
        return candidate

    def _display(self, path: Path) -> str:
        return str(path.relative_to(self.root)).replace("\\", "/")

    def _ensure_writable(self) -> None:
        if self.read_only:
            raise FilesystemError("filesystem is read-only")

    # ── operations ─────────────────────────────────────────────────────────

    def read(self, path: str) -> dict[str, object]:
        """Return file content with a relative path and a line count."""

        target = self._resolve(path)
        if not target.is_file():
            raise FilesystemError(f"not a file: {path}")
        content = target.read_text(encoding="utf-8")
        line_count = content.count("\n") + (0 if content.endswith("\n") else 1)
        return {
            "path": self._display(target),
            "line_count": line_count,
            "content": content,
        }

    def write(self, path: str, content: str) -> dict[str, object]:
        """Create or replace a file under the workspace root."""

        self._ensure_writable()
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"path": self._display(target), "written": len(content)}

    def edit(
        self, path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> dict[str, object]:
        """Replace ``old_string`` with ``new_string`` in a tracked file."""

        self._ensure_writable()
        target = self._resolve(path)
        if not target.is_file():
            raise FilesystemError(f"not a file: {path}")
        content = target.read_text(encoding="utf-8")
        occurrences = content.count(old_string)
        if occurrences == 0:
            raise FilesystemError(f"old_string not found in {path}")
        if occurrences > 1 and not replace_all:
            raise FilesystemError(
                f"old_string appears {occurrences} times in {path}; use replace_all"
            )
        new_content = content.replace(old_string, new_string)
        target.write_text(new_content, encoding="utf-8")
        return {"path": self._display(target), "replaced": occurrences}

    def glob(self, pattern: str) -> list[str]:
        """Return matching files (never directories) in stable order."""

        matches: set[str] = set()
        for candidate in sorted(self.root.rglob("*")):
            if not candidate.is_file():
                continue
            rel = self._display(candidate)
            if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(candidate.name, pattern):
                matches.add(rel)
        return sorted(matches)

    def grep(self, pattern: str, path: str | None = None) -> list[dict[str, object]]:
        """Return matching lines with line numbers, grouped by file order."""

        regex = re.compile(pattern)
        search_root = self._resolve(path) if path else self.root
        candidates = [search_root] if search_root.is_file() else sorted(search_root.rglob("*"))
        matches: list[dict[str, object]] = []
        for candidate in candidates:
            if not candidate.is_file():
                continue
            try:
                lines = candidate.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for index, line in enumerate(lines, start=1):
                if regex.search(line):
                    matches.append(GrepMatch(self._display(candidate), index, line).as_dict())
                    if len(matches) >= MAX_GREP_MATCHES:
                        return matches
        return matches
