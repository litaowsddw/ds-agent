"""Safe, deliberately narrow import helpers for external MCP and Skills.

The platform must not become an SSRF proxy just because an administrator can
connect an Agent to a third-party integration.  These helpers therefore only
accept public HTTPS endpoints and make the allowed Skill source explicit.
"""

from __future__ import annotations

import ipaddress
import json
import socket
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


MAX_IMPORT_BYTES = 256 * 1024
_REQUEST_TIMEOUT_SECONDS = 8


class ExternalImportError(ValueError):
    """A safe, user-displayable external import failure."""


@dataclass(frozen=True)
class DiscoveredMCPTool:
    name: str
    description: str
    input_schema: dict[str, object]


class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise ExternalImportError("外部服务不允许重定向")


def validate_public_https_url(url: str, *, allowed_hosts: set[str] | None = None) -> str:
    """Validate a non-local HTTPS URL before an outbound request.

    DNS is checked before every request.  It is not a substitute for egress
    firewall rules, but prevents the usual localhost/private-network SSRF
    routes and keeps this API intentionally unsuitable as a general proxy.
    """

    parsed = urlparse(url.strip())
    if parsed.scheme.lower() != "https":
        raise ExternalImportError("仅支持 HTTPS 外部地址")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ExternalImportError("外部地址格式不合法")
    if parsed.fragment:
        raise ExternalImportError("外部地址不能包含 fragment")

    hostname = parsed.hostname.lower().rstrip(".")
    if allowed_hosts is not None and hostname not in allowed_hosts:
        raise ExternalImportError("该 Skill 来源不在允许的 GitHub 域名中")
    if hostname in {"localhost", "localhost.localdomain"}:
        raise ExternalImportError("不允许连接本机或内网地址")

    try:
        addresses = socket.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ExternalImportError("无法解析外部服务地址") from exc
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address[4][0])
        except ValueError as exc:
            raise ExternalImportError("外部服务地址不合法") from exc
        if not ip.is_global:
            raise ExternalImportError("不允许连接本机或内网地址")
    return parsed.geturl()


def normalize_github_skill_url(source_url: str, skill_path: str | None = None) -> str:
    """Accept only a raw GitHub SKILL.md URL or a github.com file/tree link."""

    parsed = urlparse(source_url.strip())
    host = parsed.hostname.lower().rstrip(".") if parsed.hostname else ""
    if host == "raw.githubusercontent.com":
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) < 4 or path_parts[-1] != "SKILL.md":
            raise ExternalImportError("GitHub raw 地址必须直接指向 SKILL.md")
        return validate_public_https_url(source_url, allowed_hosts={"raw.githubusercontent.com"})

    if host != "github.com":
        raise ExternalImportError("Skill 只支持 github.com 文件链接或 raw.githubusercontent.com SKILL.md")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 5 or parts[2] not in {"blob", "tree"}:
        raise ExternalImportError("请提供 GitHub 的 SKILL.md 文件链接")
    owner, repository, _kind, ref, *path_parts = parts
    if not path_parts or path_parts[-1] != "SKILL.md":
        raise ExternalImportError("GitHub 链接必须直接指向 SKILL.md")
    if skill_path:
        # A file link is unambiguous.  Reject a second path rather than silently
        # importing a different file than the one reviewed by the user.
        raise ExternalImportError("GitHub 文件链接不需要额外的 skill_path")
    raw_url = f"https://raw.githubusercontent.com/{owner}/{repository}/{ref}/{'/'.join(path_parts)}"
    return validate_public_https_url(raw_url, allowed_hosts={"raw.githubusercontent.com"})


def fetch_github_skill(source_url: str, skill_path: str | None = None) -> tuple[str, str]:
    """Fetch one reviewed GitHub SKILL.md with bounded, no-redirect IO."""

    resolved_url = normalize_github_skill_url(source_url, skill_path)
    payload, _headers = _fetch_bytes(resolved_url, headers={"Accept": "text/plain"})
    if len(payload) > MAX_IMPORT_BYTES:
        raise ExternalImportError("Skill 文件超过 256 KiB 限制")
    try:
        return payload.decode("utf-8"), resolved_url
    except UnicodeDecodeError as exc:
        raise ExternalImportError("Skill 文件必须是 UTF-8 文本") from exc


def discover_streamable_http_tools(url: str, headers: dict[str, str]) -> list[DiscoveredMCPTool]:
    """Perform MCP initialize + tools/list for a Streamable HTTP server.

    Legacy SSE/stdio transports intentionally are not tunneled by this web
    service.  They need a separately managed connector process.
    """

    endpoint = validate_public_https_url(url)
    request_headers = _safe_mcp_headers(headers)
    initialize = _mcp_request(
        endpoint,
        request_headers,
        request_id=1,
        method="initialize",
        params={
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "ds-agent", "version": "1.0"},
        },
    )
    if "error" in initialize:
        raise ExternalImportError(f"MCP initialize 失败: {_rpc_error_text(initialize['error'])}")

    session_id = str(initialize.get("_mcp_session_id") or "")
    if session_id:
        request_headers["Mcp-Session-Id"] = session_id
    tool_result = _mcp_request(endpoint, request_headers, request_id=2, method="tools/list", params={})
    if "error" in tool_result:
        raise ExternalImportError(f"MCP tools/list 失败: {_rpc_error_text(tool_result['error'])}")
    result = tool_result.get("result")
    raw_tools = result.get("tools") if isinstance(result, dict) else None
    if not isinstance(raw_tools, list):
        raise ExternalImportError("MCP tools/list 返回格式无效")

    tools: list[DiscoveredMCPTool] = []
    seen_names: set[str] = set()
    for item in raw_tools:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name or len(name) > 128 or name in seen_names:
            continue
        input_schema = item.get("inputSchema", item.get("input_schema", {}))
        if not isinstance(input_schema, dict):
            input_schema = {}
        tools.append(
            DiscoveredMCPTool(
                name=name,
                description=str(item.get("description") or "").strip()[:8000],
                input_schema=input_schema,
            )
        )
        seen_names.add(name)
    if not tools:
        raise ExternalImportError("该 MCP 服务未发现可导入工具")
    return tools


def invoke_streamable_http_tool(
    url: str,
    headers: dict[str, str],
    *,
    tool_name: str,
    arguments: dict[str, object],
) -> dict[str, Any]:
    """Invoke one imported Streamable HTTP MCP tool.

    This deliberately shares the import-time transport boundary: only a public
    HTTPS endpoint, bounded requests/responses, no redirects, and the small
    allow-list of credential headers are supported.  It is *not* a generic
    HTTP action node.  Callers must still perform their Agent authorization and
    human-approval checks before reaching this function.

    A new MCP session is established per workflow node invocation.  Persisting
    a session ID across Workflow runs would create cross-run state and makes
    audit/retry semantics ambiguous, so it is intentionally avoided here.
    """

    if not tool_name or len(tool_name) > 128:
        raise ExternalImportError("MCP Tool 名称不合法")
    if not isinstance(arguments, dict):
        raise ExternalImportError("MCP Tool 参数必须是 JSON 对象")

    endpoint = validate_public_https_url(url)
    request_headers = _safe_mcp_headers(headers)
    initialize = _mcp_request(
        endpoint,
        request_headers,
        request_id=1,
        method="initialize",
        params={
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "ds-agent", "version": "1.0"},
        },
    )
    if "error" in initialize:
        raise ExternalImportError(f"MCP initialize 失败: {_rpc_error_text(initialize['error'])}")

    session_id = str(initialize.get("_mcp_session_id") or "")
    if session_id:
        request_headers["Mcp-Session-Id"] = session_id
    tool_result = _mcp_request(
        endpoint,
        request_headers,
        request_id=2,
        method="tools/call",
        params={"name": tool_name, "arguments": arguments},
    )
    if "error" in tool_result:
        raise ExternalImportError(f"MCP Tool 调用失败: {_rpc_error_text(tool_result['error'])}")

    result = tool_result.get("result")
    if not isinstance(result, dict):
        raise ExternalImportError("MCP Tool 返回格式无效")
    if result.get("isError") is True:
        raise ExternalImportError(f"MCP Tool 执行失败: {_mcp_tool_error_text(result)}")
    return result


def _safe_mcp_headers(headers: dict[str, str]) -> dict[str, str]:
    accepted: dict[str, str] = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    for name, value in headers.items():
        normalized = str(name).strip()
        if normalized.lower() in {"host", "content-length", "content-type", "accept", "mcp-session-id"}:
            raise ExternalImportError(f"不允许设置 MCP 请求头: {normalized}")
        if not (normalized.lower() == "authorization" or normalized.lower() == "x-api-key" or normalized.lower().startswith("x-")):
            raise ExternalImportError("凭据仅支持 Authorization、X-API-Key 或 X-* 请求头")
        text = str(value)
        if not text or "\r" in text or "\n" in text:
            raise ExternalImportError("MCP 请求头值不合法")
        accepted[normalized] = text
    return accepted


def _mcp_request(
    endpoint: str,
    headers: dict[str, str],
    *,
    request_id: int,
    method: str,
    params: dict[str, object],
) -> dict[str, Any]:
    body = json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}).encode("utf-8")
    payload, response_headers = _fetch_bytes(endpoint, headers=headers, data=body)
    response = _parse_mcp_response(payload)
    session_id = response_headers.get("Mcp-Session-Id") or response_headers.get("mcp-session-id")
    if session_id:
        response["_mcp_session_id"] = session_id
    return response


def _fetch_bytes(url: str, *, headers: dict[str, str], data: bytes | None = None) -> tuple[bytes, Any]:
    request = Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    opener = build_opener(_RejectRedirect())
    try:
        with opener.open(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            payload = response.read(MAX_IMPORT_BYTES + 1)
            if len(payload) > MAX_IMPORT_BYTES:
                raise ExternalImportError("外部响应超过 256 KiB 限制")
            return payload, response.headers
    except ExternalImportError:
        raise
    except HTTPError as exc:
        raise ExternalImportError(f"外部服务返回 HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise ExternalImportError("无法连接外部服务") from exc


def _parse_mcp_response(payload: bytes) -> dict[str, Any]:
    text = payload.decode("utf-8", errors="replace").strip()
    if text.startswith("data:"):
        text = "\n".join(line[5:].strip() for line in text.splitlines() if line.startswith("data:")).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExternalImportError("MCP 服务未返回 JSON-RPC 响应") from exc
    if not isinstance(parsed, dict) or parsed.get("jsonrpc") != "2.0":
        raise ExternalImportError("MCP 服务返回了无效 JSON-RPC 响应")
    return parsed


def _rpc_error_text(error: object) -> str:
    return str(error.get("message") if isinstance(error, dict) else error)[:400]


def _mcp_tool_error_text(result: dict[str, Any]) -> str:
    """Extract a bounded, display-safe error message from an MCP tool result."""

    content = result.get("content")
    if isinstance(content, list):
        messages = [
            str(item.get("text") or "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        text = " ".join(message for message in messages if message)
        if text:
            return text[:400]
    return "远端 MCP Tool 返回 isError"
