"""Workflow MCP Tool execution safety and audit contracts."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.app.main import app
from apps.api.app.routes import mcp as mcp_routes
from app.services import workflow_execution as workflow_execution_module
from app.services.workflow_execution import (
    _load_mcp_credential_headers,
    _validate_mcp_tool_arguments,
)
from app.services.external_import import DiscoveredMCPTool


def _suffix(label: str) -> str:
    return f"{label}-{uuid4().hex[:8]}"


def _create_owner_org_agent(client: TestClient, suffix: str) -> tuple[str, str, str, dict[str, str]]:
    owner_user_id = client.post(
        "/identity/users/register",
        json={
            "email": f"owner-{suffix}@example.com",
            "display_name": "Owner",
            "password": "password123",
        },
    ).json()["user_id"]
    org_id = client.post(
        "/identity/organizations",
        json={"creator_user_id": owner_user_id, "name": f"Org {suffix}"},
    ).json()["org_id"]
    login = client.post(
        "/identity/users/login",
        json={"email": f"owner-{suffix}@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['token']['access_token']}"}
    agent_id = client.post(
        "/agents",
        json={
            "actor_user_id": owner_user_id,
            "org_id": org_id,
            "name": f"Agent {suffix}",
            "description": "",
        },
        headers=headers,
    ).json()["agent_id"]
    return owner_user_id, org_id, agent_id, headers


def _bind_mcp_tool(
    client: TestClient,
    *,
    monkeypatch,
    actor_user_id: str,
    org_id: str,
    agent_id: str,
    risk_level: str = "low",
    input_schema: dict[str, object] | None = None,
) -> str:
    schema = input_schema or {"type": "object"}
    monkeypatch.setattr(
        mcp_routes,
        "discover_streamable_http_tools",
        lambda *_args, **_kwargs: [
            DiscoveredMCPTool(
                name="search_docs",
                description="Search docs",
                input_schema=schema,
            )
        ],
    )
    import_response = client.post(
        f"/mcp/agents/{agent_id}/import",
        json={
            "actor_user_id": actor_user_id,
            "name": "Imported MCP",
            "transport": "streamable_http",
            "url": "https://mcp.example.com/mcp",
            "credentials": {},
        },
    )
    assert import_response.status_code == 200
    server_id = import_response.json()["server"]["server_id"]
    if risk_level == "low":
        return import_response.json()["tools"][0]["tool_id"]
    tool_response = client.post(
        f"/mcp/servers/{server_id}/tools",
        json={
            "actor_user_id": actor_user_id,
            "name": "search_docs",
            "description": "Search docs",
            "input_schema": schema,
            "risk_level": risk_level,
        },
    )
    assert tool_response.status_code == 200
    return tool_response.json()["tool_id"]


def _publish_tool_workflow(
    client: TestClient,
    *,
    actor_user_id: str,
    agent_id: str,
    tool_id: str,
    config: dict[str, object],
) -> str:
    workflow = client.post(
        "/workflows",
        json={
            "actor_user_id": actor_user_id,
            "agent_id": agent_id,
            "name": "MCP workflow",
            "description": "",
            "draft_definition": {
                "version": "1.0",
                "nodes": [
                    {"id": "start", "type": "start", "config": {}},
                    {"id": "tool", "type": "tool", "config": {"tool_id": tool_id, **config}},
                    {"id": "end", "type": "end", "config": {}},
                ],
                "edges": [
                    {"source": "start", "target": "tool"},
                    {"source": "tool", "target": "end"},
                ],
            },
        },
    )
    assert workflow.status_code == 200
    publish = client.post(
        f"/workflows/{workflow.json()['workflow_id']}/publish",
        json={"actor_user_id": actor_user_id},
    )
    assert publish.status_code == 200
    return publish.json()["version_id"]


def test_legacy_mcp_without_import_envelope_is_not_executable() -> None:
    """Existing registry rows with empty credentials must not gain runtime access."""

    with pytest.raises(ValueError, match="受控导入"):
        _load_mcp_credential_headers("")


def test_mcp_input_schema_rejects_external_ref_without_fetching_it() -> None:
    with pytest.raises(ValueError, match=r"外部 \$ref"):
        _validate_mcp_tool_arguments(
            '{"$ref":"https://untrusted.example/schema.json"}',
            {},
        )


def test_manual_streamable_http_registration_requires_controlled_import() -> None:
    with TestClient(app) as client:
        actor_user_id, org_id, _agent_id, _headers = _create_owner_org_agent(
            client, _suffix("wf-mcp-legacy-register")
        )
        response = client.post(
            "/mcp/servers",
            json={
                "actor_user_id": actor_user_id,
                "org_id": org_id,
                "name": "Legacy MCP",
                "transport": "streamable_http",
                "url": "https://mcp.example.com/mcp",
            },
        )

        assert response.status_code == 400
        assert "受控导入" in response.json()["detail"]


def test_workflow_tool_executes_authorized_low_risk_mcp_and_audits(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_tool_call(url, headers, *, tool_name, arguments):
        calls.append(
            {
                "url": url,
                "headers": headers,
                "tool_name": tool_name,
                "arguments": arguments,
            }
        )
        return {"content": [{"type": "text", "text": "one result"}]}

    monkeypatch.setattr(workflow_execution_module, "invoke_streamable_http_tool", fake_tool_call)

    with TestClient(app) as client:
        actor_user_id, org_id, agent_id, owner_headers = _create_owner_org_agent(
            client, _suffix("wf-mcp-execute")
        )
        tool_id = _bind_mcp_tool(
            client,
            monkeypatch=monkeypatch,
            actor_user_id=actor_user_id,
            org_id=org_id,
            agent_id=agent_id,
        )
        version_id = _publish_tool_workflow(
            client,
            actor_user_id=actor_user_id,
            agent_id=agent_id,
            tool_id=tool_id,
            config={"arguments": {"q": "{{input.query}}", "limit": 3}},
        )

        response = client.post(
            "/workflow-runs",
            json={"version_id": version_id, "input_data": {"query": "MCP"}},
            headers=owner_headers,
        )

        assert response.status_code == 200
        run = response.json()
        assert run["status"] == "succeeded", run["error_message"]
        assert calls == [
            {
                "url": "https://mcp.example.com/mcp",
                "headers": {},
                "tool_name": "search_docs",
                "arguments": {"q": "MCP", "limit": 3},
            }
        ]
        nodes = client.get(
            f"/workflow-runs/{run['run_id']}/nodes",
            params={"actor_user_id": actor_user_id},
        ).json()
        tool_node = next(node for node in nodes if node["node_id"] == "tool")
        assert tool_node["output_data"]["arguments"] == {"q": "MCP", "limit": 3}
        assert tool_node["output_data"]["result"]["content"][0]["text"] == "one result"

        audit_logs = client.get(
            f"/identity/organizations/{org_id}/audit-logs",
            params={"actor_user_id": actor_user_id},
        )
        assert audit_logs.status_code == 200
        events = [
            event
            for event in audit_logs.json()
            if event["action"].startswith("workflow.mcp_tool.")
        ]
        assert [event["action"] for event in events] == [
            "workflow.mcp_tool.started",
            "workflow.mcp_tool.succeeded",
        ]
        assert events[-1]["detail"]["workflow_run_id"] == run["run_id"]
        assert events[-1]["detail"]["arguments"] == {"q": "MCP", "limit": 3}


def test_workflow_tool_refuses_unapproved_high_risk_snapshot(monkeypatch) -> None:
    def must_not_call(*_args, **_kwargs):
        raise AssertionError("high-risk MCP Tool must not be called before approval")

    monkeypatch.setattr(workflow_execution_module, "invoke_streamable_http_tool", must_not_call)

    with TestClient(app) as client:
        actor_user_id, org_id, agent_id, owner_headers = _create_owner_org_agent(
            client, _suffix("wf-mcp-approval")
        )
        tool_id = _bind_mcp_tool(
            client,
            monkeypatch=monkeypatch,
            actor_user_id=actor_user_id,
            org_id=org_id,
            agent_id=agent_id,
            risk_level="high",
        )
        version_id = _publish_tool_workflow(
            client,
            actor_user_id=actor_user_id,
            agent_id=agent_id,
            tool_id=tool_id,
            config={
                # Canvas data cannot downgrade the risk level stored in the MCP snapshot.
                "risk_level": "low",
                "arguments": {"id": "{{input.id}}"},
            },
        )

        response = client.post(
            "/workflow-runs",
            json={"version_id": version_id, "input_data": {"id": "record-1"}},
            headers=owner_headers,
        )

        assert response.status_code == 200
        run = response.json()
        assert run["status"] == "failed"
        nodes = client.get(
            f"/workflow-runs/{run['run_id']}/nodes",
            params={"actor_user_id": actor_user_id},
        ).json()
        tool_node = next(node for node in nodes if node["node_id"] == "tool")
        assert tool_node["status"] == "failed"
        assert "需要人工审批" in tool_node["error_message"]

        audit_logs = client.get(
            f"/identity/organizations/{org_id}/audit-logs",
            params={"actor_user_id": actor_user_id},
        ).json()
        approval_events = [
            event
            for event in audit_logs
            if event["action"] == "workflow.mcp_tool.approval_required"
        ]
        assert len(approval_events) == 1
        assert approval_events[0]["detail"]["arguments"] == {"id": "record-1"}


def test_workflow_tool_rejects_arguments_that_violate_imported_schema(monkeypatch) -> None:
    def must_not_call(*_args, **_kwargs):
        raise AssertionError("invalid Tool arguments must not reach the MCP server")

    monkeypatch.setattr(workflow_execution_module, "invoke_streamable_http_tool", must_not_call)

    with TestClient(app) as client:
        actor_user_id, org_id, agent_id, owner_headers = _create_owner_org_agent(
            client, _suffix("wf-mcp-schema")
        )
        tool_id = _bind_mcp_tool(
            client,
            monkeypatch=monkeypatch,
            actor_user_id=actor_user_id,
            org_id=org_id,
            agent_id=agent_id,
            input_schema={
                "type": "object",
                "properties": {"q": {"type": "string"}},
                "required": ["q"],
                "additionalProperties": False,
            },
        )
        version_id = _publish_tool_workflow(
            client,
            actor_user_id=actor_user_id,
            agent_id=agent_id,
            tool_id=tool_id,
            config={"arguments": {"q": 42}},
        )

        response = client.post(
            "/workflow-runs",
            json={"version_id": version_id, "input_data": {}},
            headers=owner_headers,
        )

        assert response.status_code == 200
        run = response.json()
        assert run["status"] == "failed"
        assert "input_schema 校验" in run["error_message"]
        audit_logs = client.get(
            f"/identity/organizations/{org_id}/audit-logs",
            params={"actor_user_id": actor_user_id},
        ).json()
        rejected = [
            event
            for event in audit_logs
            if event["action"] == "workflow.mcp_tool.rejected"
        ]
        assert len(rejected) == 1
        assert rejected[0]["detail"]["arguments"] == {"q": 42}
