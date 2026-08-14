"""Filesystem tools → LangChain BaseTool wrappers.

Models DeepSeek Harness ``dsh-tool-fs`` / ``dsh-tool-fs-search`` /
``dsh-tool-str-replace-editor``.  Every tool delegates to an injected
``filesystem`` accessor (see ``packages/runtime/filesystem.py``); an
unconfigured tool fails honestly instead of inventing file contents.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from langchain_core.tools import BaseTool


def _call(filesystem: Any, operation: Callable[[Any], object]) -> str:
    if filesystem is None:
        return json.dumps({"error": "Filesystem is not configured"}, ensure_ascii=False)
    try:
        result = operation(filesystem)
        return json.dumps(result, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


class ReadFileTool(BaseTool):
    """Read a UTF-8 text file under the workspace root."""

    name: str = "read_file"
    description: str = (
        "Read a UTF-8 text file under the agent workspace root and return its "
        "content plus a line count. Use this to inspect files before editing."
    )
    filesystem: Any = None

    class Config:
        arbitrary_types_allowed = True

    def _run(self, path: str, **kwargs: Any) -> str:
        return _call(self.filesystem, lambda fs: fs.read(path))

    async def _arun(self, path: str, **kwargs: Any) -> str:
        return _call(self.filesystem, lambda fs: fs.read(path))


class WriteFileTool(BaseTool):
    """Create or fully replace a file under the workspace root."""

    name: str = "write_file"
    description: str = (
        "Create or fully replace a UTF-8 text file under the agent workspace "
        "root. Existing content is overwritten; read the file first if you only "
        "need a targeted change."
    )
    filesystem: Any = None

    class Config:
        arbitrary_types_allowed = True

    def _run(self, path: str, content: str, **kwargs: Any) -> str:
        return _call(self.filesystem, lambda fs: fs.write(path, content))

    async def _arun(self, path: str, content: str, **kwargs: Any) -> str:
        return _call(self.filesystem, lambda fs: fs.write(path, content))


class EditFileTool(BaseTool):
    """Targeted literal replacement inside a file."""

    name: str = "edit_file"
    description: str = (
        "Replace one literal old_string with new_string in a workspace file. The "
        "old_string must appear exactly once unless replace_all is true."
    )
    filesystem: Any = None

    class Config:
        arbitrary_types_allowed = True

    def _run(
        self, path: str, old_string: str, new_string: str, replace_all: bool = False, **kwargs: Any
    ) -> str:
        return _call(
            self.filesystem, lambda fs: fs.edit(path, old_string, new_string, replace_all)
        )

    async def _arun(
        self, path: str, old_string: str, new_string: str, replace_all: bool = False, **kwargs: Any
    ) -> str:
        return _call(
            self.filesystem, lambda fs: fs.edit(path, old_string, new_string, replace_all)
        )


class GlobTool(BaseTool):
    """Find workspace files matching a path pattern."""

    name: str = "glob_files"
    description: str = (
        "Find files under the agent workspace root whose path or basename matches "
        "a glob pattern (e.g. '**/*.py' or '*.md'). Returns file paths only."
    )
    filesystem: Any = None

    class Config:
        arbitrary_types_allowed = True

    def _run(self, pattern: str, **kwargs: Any) -> str:
        return _call(self.filesystem, lambda fs: fs.glob(pattern))

    async def _arun(self, pattern: str, **kwargs: Any) -> str:
        return _call(self.filesystem, lambda fs: fs.glob(pattern))


class GrepTool(BaseTool):
    """Search workspace file contents with a regular expression."""

    name: str = "grep_files"
    description: str = (
        "Search workspace file contents with a regular expression. Returns "
        "matching lines with their file path and line number."
    )
    filesystem: Any = None

    class Config:
        arbitrary_types_allowed = True

    def _run(self, pattern: str, path: str | None = None, **kwargs: Any) -> str:
        return _call(self.filesystem, lambda fs: fs.grep(pattern, path))

    async def _arun(self, pattern: str, path: str | None = None, **kwargs: Any) -> str:
        return _call(self.filesystem, lambda fs: fs.grep(pattern, path))
