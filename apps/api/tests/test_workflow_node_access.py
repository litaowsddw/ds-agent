"""Authorization boundaries for workflow run node-list access."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import HTTPException

from apps.api.app.routes import workflow_runs


@dataclass
class _Run:
    run_id: str
    org_id: str


class _WorkflowRunDB:
    def __init__(self, runs: dict[str, _Run]) -> None:
        self.runs = runs

    async def get_run_required(self, session: object, run_id: str) -> _Run:
        try:
            return self.runs[run_id]
        except KeyError as exc:
            raise ValueError("run not found") from exc


class _MembershipDB:
    def __init__(self, memberships: dict[str, set[str]]) -> None:
        self.memberships = memberships

    async def assert_org_access(
        self, session: object, user_id: str, org_id: str, required_role: str | None = None
    ) -> object:
        if org_id not in self.memberships.get(user_id, set()):
            raise ValueError("no access")
        return object()


@pytest.mark.asyncio
async def test_list_node_runs_returns_404_when_run_does_not_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(workflow_runs, "workflow_run_db", _WorkflowRunDB({}))

    with pytest.raises(HTTPException) as exc_info:
        await workflow_runs.list_node_runs(
            run_id="missing-run",
            actor_user_id="user-a",
            session=object(),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_list_node_runs_returns_403_for_existing_cross_org_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        workflow_runs,
        "workflow_run_db",
        _WorkflowRunDB({"run-org-a": _Run(run_id="run-org-a", org_id="org-a")}),
    )
    monkeypatch.setattr(workflow_runs, "membership_db", _MembershipDB({"user-b": {"org-b"}}))

    with pytest.raises(HTTPException) as exc_info:
        await workflow_runs.list_node_runs(
            run_id="run-org-a",
            actor_user_id="user-b",
            session=object(),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Forbidden"
