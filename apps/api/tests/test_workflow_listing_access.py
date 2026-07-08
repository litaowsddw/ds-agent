"""Access-control tests for Workflow and Workflow Run listing routes."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from fastapi import HTTPException

from apps.api.app.routes import workflow_runs, workflows


@dataclass
class _Agent:
    agent_id: str
    org_id: str


@dataclass
class _Workflow:
    workflow_id: str
    org_id: str
    agent_id: str
    name: str = "Workflow"
    description: str = ""
    draft_definition: str = json.dumps({"version": "1.0", "nodes": [], "edges": []})
    published_version_id: str | None = None
    created_by: str = "user-a"


@dataclass
class _Run:
    run_id: str
    org_id: str
    workflow_id: str
    version_id: str = "version-a"
    agent_id: str = "agent-a"
    input_data: str = json.dumps({"text": "hello"})
    status: str = "succeeded"
    output_data: str = json.dumps({"text": "hello"})
    error_message: str = ""
    created_by: str = "user-a"


class _MembershipDB:
    def __init__(self, memberships: dict[str, set[str]]) -> None:
        self.memberships = memberships

    async def assert_org_access(
        self,
        session: object,
        user_id: str,
        org_id: str,
        required_role: str | None = None,
    ) -> object:
        if org_id not in self.memberships.get(user_id, set()):
            raise ValueError("no access")
        return object()


class _AgentDB:
    def __init__(self, agents: dict[str, _Agent]) -> None:
        self.agents = agents

    async def get_agent_required(self, session: object, agent_id: str) -> _Agent:
        return self.agents[agent_id]


class _WorkflowDB:
    def __init__(
        self,
        workflows_by_id: dict[str, _Workflow] | None = None,
        listed_workflows: list[_Workflow] | None = None,
    ) -> None:
        self.workflows_by_id = workflows_by_id or {}
        self.listed_workflows = listed_workflows or []

    async def get_workflow_required(self, session: object, workflow_id: str) -> _Workflow:
        return self.workflows_by_id[workflow_id]

    async def list_workflows(
        self,
        session: object,
        org_id: str | None = None,
        agent_id: str | None = None,
    ) -> tuple[list[_Workflow], int]:
        return self.listed_workflows, len(self.listed_workflows)


class _WorkflowRunDB:
    def __init__(self, listed_runs: list[_Run]) -> None:
        self.listed_runs = listed_runs

    async def list_workflow_runs(
        self,
        session: object,
        workflow_id: str,
    ) -> tuple[list[_Run], int]:
        return self.listed_runs, len(self.listed_runs)


@pytest.mark.asyncio
async def test_list_workflows_rejects_cross_org_user_for_agent_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        workflows,
        "agent_db",
        _AgentDB({"agent-a": _Agent("agent-a", "org-a")}),
    )
    monkeypatch.setattr(workflows, "membership_db", _MembershipDB({"user-b": {"org-b"}}))
    monkeypatch.setattr(workflows, "workflow_db", _WorkflowDB())

    with pytest.raises(HTTPException) as exc_info:
        await workflows.list_workflows(
            actor_user_id="user-b",
            org_id=None,
            agent_id="agent-a",
            session=object(),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_list_workflows_accepts_same_org_agent_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = _Workflow(workflow_id="workflow-a", org_id="org-a", agent_id="agent-a")
    monkeypatch.setattr(
        workflows,
        "agent_db",
        _AgentDB({"agent-a": _Agent("agent-a", "org-a")}),
    )
    monkeypatch.setattr(workflows, "membership_db", _MembershipDB({"user-a": {"org-a"}}))
    monkeypatch.setattr(workflows, "workflow_db", _WorkflowDB(listed_workflows=[workflow]))

    response = await workflows.list_workflows(
        actor_user_id="user-a",
        org_id=None,
        agent_id="agent-a",
        session=object(),  # type: ignore[arg-type]
    )

    assert [item.workflow_id for item in response] == ["workflow-a"]


@pytest.mark.asyncio
async def test_list_workflows_rejects_org_id_that_does_not_match_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        workflows,
        "agent_db",
        _AgentDB({"agent-a": _Agent("agent-a", "org-a")}),
    )
    monkeypatch.setattr(
        workflows,
        "membership_db",
        _MembershipDB({"user-a": {"org-a", "org-b"}}),
    )
    monkeypatch.setattr(workflows, "workflow_db", _WorkflowDB())

    with pytest.raises(HTTPException) as exc_info:
        await workflows.list_workflows(
            actor_user_id="user-a",
            org_id="org-b",
            agent_id="agent-a",
            session=object(),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_list_runs_rejects_cross_org_user_for_workflow_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = _Workflow(workflow_id="workflow-a", org_id="org-a", agent_id="agent-a")
    monkeypatch.setattr(workflow_runs, "workflow_db", _WorkflowDB({"workflow-a": workflow}))
    monkeypatch.setattr(
        workflow_runs,
        "membership_db",
        _MembershipDB({"user-b": {"org-b"}}),
    )
    monkeypatch.setattr(workflow_runs, "workflow_run_db", _WorkflowRunDB([]))

    with pytest.raises(HTTPException) as exc_info:
        await workflow_runs.list_runs(
            actor_user_id="user-b",
            workflow_id="workflow-a",
            org_id=None,
            session=object(),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_list_runs_accepts_same_org_workflow_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = _Workflow(workflow_id="workflow-a", org_id="org-a", agent_id="agent-a")
    run = _Run(run_id="run-a", org_id="org-a", workflow_id="workflow-a")
    monkeypatch.setattr(workflow_runs, "workflow_db", _WorkflowDB({"workflow-a": workflow}))
    monkeypatch.setattr(
        workflow_runs,
        "membership_db",
        _MembershipDB({"user-a": {"org-a"}}),
    )
    monkeypatch.setattr(workflow_runs, "workflow_run_db", _WorkflowRunDB([run]))

    response = await workflow_runs.list_runs(
        actor_user_id="user-a",
        workflow_id="workflow-a",
        org_id=None,
        session=object(),  # type: ignore[arg-type]
    )

    assert [item.run_id for item in response] == ["run-a"]
