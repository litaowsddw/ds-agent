"""Safety and protocol tests for external MCP/Skill imports."""

from __future__ import annotations

import pytest

from app.services import external_import
from app.services.external_import import (
    ExternalImportError,
    discover_streamable_http_tools,
    fetch_github_skill,
    normalize_github_skill_url,
    validate_public_https_url,
)


def _public_dns(*_args, **_kwargs):
    return [(2, 1, 6, "", ("8.8.8.8", 443))]


def test_external_import_rejects_non_https_before_network() -> None:
    with pytest.raises(ExternalImportError, match="HTTPS"):
        validate_public_https_url("http://example.com/mcp")


def test_external_import_rejects_private_resolved_address(monkeypatch) -> None:
    monkeypatch.setattr(
        external_import.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(ExternalImportError, match="内网"):
        validate_public_https_url("https://example.com/mcp")


def test_github_skill_import_only_accepts_exact_skill_file(monkeypatch) -> None:
    monkeypatch.setattr(external_import.socket, "getaddrinfo", _public_dns)
    assert normalize_github_skill_url(
        "https://github.com/acme/skills/blob/main/example/SKILL.md"
    ) == "https://raw.githubusercontent.com/acme/skills/main/example/SKILL.md"
    with pytest.raises(ExternalImportError, match="SKILL.md"):
        normalize_github_skill_url("https://github.com/acme/skills/blob/main/README.md")


def test_github_skill_import_is_bounded_and_utf8(monkeypatch) -> None:
    monkeypatch.setattr(external_import.socket, "getaddrinfo", _public_dns)
    monkeypatch.setattr(
        external_import,
        "_fetch_bytes",
        lambda *_args, **_kwargs: (b"---\nname: sample\ndescription: Example\n---\n", {}),
    )
    content, source = fetch_github_skill("https://raw.githubusercontent.com/acme/skills/main/SKILL.md")
    assert content.startswith("---")
    assert source.endswith("/SKILL.md")


def test_streamable_mcp_discovery_imports_all_declared_tools(monkeypatch) -> None:
    monkeypatch.setattr(external_import.socket, "getaddrinfo", _public_dns)
    responses = iter(
        [
            {"jsonrpc": "2.0", "id": 1, "result": {}, "_mcp_session_id": "session-1"},
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {
                    "tools": [
                        {
                            "name": "search_docs",
                            "description": "Search the public docs",
                            "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}},
                        }
                    ]
                },
            },
        ]
    )
    monkeypatch.setattr(external_import, "_mcp_request", lambda *_args, **_kwargs: next(responses))

    tools = discover_streamable_http_tools("https://mcp.example.com/mcp", {"Authorization": "Bearer test"})

    assert [(tool.name, tool.description) for tool in tools] == [("search_docs", "Search the public docs")]
