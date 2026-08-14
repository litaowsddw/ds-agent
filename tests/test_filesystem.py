"""Workspace filesystem accessor and its tool wrappers."""

import json

import pytest

from packages.runtime.filesystem import FilesystemError, LocalFilesystem
from packages.runtime.tools.fs_tool import (
    EditFileTool,
    GlobTool,
    GrepTool,
    ReadFileTool,
    WriteFileTool,
)


def _make_fs(tmp_path, read_only: bool = False) -> LocalFilesystem:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "a.txt").write_text("hello world\n", encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "b.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    return LocalFilesystem(root, read_only=read_only)


def test_read_reports_relative_path_and_line_count(tmp_path) -> None:
    fs = _make_fs(tmp_path)
    result = fs.read("a.txt")
    assert result["path"] == "a.txt"
    assert result["content"] == "hello world\n"
    assert result["line_count"] == 1


def test_write_creates_parent_dirs_and_reads_back(tmp_path) -> None:
    fs = _make_fs(tmp_path)
    fs.write("nested/deep/c.md", "# title\n")
    assert fs.read("nested/deep/c.md")["content"] == "# title\n"


def test_glob_returns_files_never_directories(tmp_path) -> None:
    fs = _make_fs(tmp_path)
    assert fs.glob("*.py") == ["sub/b.py"]
    assert "a.txt" in fs.glob("*")
    assert "sub" not in fs.glob("*")


def test_grep_returns_matching_lines_with_numbers(tmp_path) -> None:
    fs = _make_fs(tmp_path)
    assert fs.grep("return 1", path="sub") == [
        {"path": "sub/b.py", "line_number": 2, "text": "    return 1"}
    ]


def test_edit_single_and_replace_all(tmp_path) -> None:
    fs = _make_fs(tmp_path)
    fs.write("d.txt", "aa bb aa\n")

    result = fs.edit("d.txt", "bb", "cc")
    assert fs.read("d.txt")["content"] == "aa cc aa\n"
    assert result["replaced"] == 1

    result = fs.edit("d.txt", "aa", "xx", replace_all=True)
    assert fs.read("d.txt")["content"] == "xx cc xx\n"
    assert result["replaced"] == 2

    with pytest.raises(FilesystemError):
        fs.edit("d.txt", "xx", "yy")  # appears twice without replace_all


def test_path_traversal_is_rejected(tmp_path) -> None:
    fs = _make_fs(tmp_path)
    with pytest.raises(FilesystemError):
        fs.read("../secret.txt")
    with pytest.raises(FilesystemError):
        fs.write("../escape.txt", "x")


def test_read_only_filesystem_rejects_writes(tmp_path) -> None:
    fs = _make_fs(tmp_path, read_only=True)
    assert fs.read("a.txt")["content"] == "hello world\n"
    with pytest.raises(FilesystemError):
        fs.write("x.txt", "x")
    with pytest.raises(FilesystemError):
        fs.edit("a.txt", "hello", "bye")


@pytest.mark.asyncio
async def test_fs_tools_wrap_filesystem(tmp_path) -> None:
    fs = _make_fs(tmp_path)

    read = json.loads(await ReadFileTool(filesystem=fs).ainvoke({"path": "a.txt"}))
    assert read["content"] == "hello world\n"

    write = json.loads(
        await WriteFileTool(filesystem=fs).ainvoke({"path": "new.txt", "content": "abc"})
    )
    assert write["written"] == 3

    globbed = json.loads(await GlobTool(filesystem=fs).ainvoke({"pattern": "*"}))
    assert "a.txt" in globbed

    matches = json.loads(await GrepTool(filesystem=fs).ainvoke({"pattern": "return 1"}))
    assert matches[0]["path"] == "sub/b.py"

    await EditFileTool(filesystem=fs).ainvoke(
        {"path": "a.txt", "old_string": "world", "new_string": "there"}
    )
    assert fs.read("a.txt")["content"] == "hello there\n"


@pytest.mark.asyncio
async def test_fs_tools_fail_honestly_without_filesystem() -> None:
    assert json.loads(await ReadFileTool().ainvoke({"path": "x"})) == {
        "error": "Filesystem is not configured"
    }
