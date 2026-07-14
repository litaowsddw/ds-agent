"""Workflow worker task contract tests."""

import sys
from contextlib import AbstractAsyncContextManager
from types import ModuleType, SimpleNamespace

import pytest

from apps.worker.app.tasks import workflow


class _SessionContext(AbstractAsyncContextManager):
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return False

    async def commit(self) -> None:
        pass


@pytest.mark.asyncio
async def test_workflow_worker_rebuilds_execution_from_persisted_run(monkeypatch) -> None:
    """Queued definition/input must not override the run stored by the API."""

    run = SimpleNamespace(
        version_id="version_1",
        input_data='{"text": "trusted"}',
        created_by="user_1",
    )
    version = SimpleNamespace(definition='{"nodes": [{"id": "trusted"}]}')
    captured: dict[str, object] = {}

    class RunStore:
        async def get_run_required(self, session, run_id):
            captured["run_id"] = run_id
            return run

    class VersionStore:
        async def get_by_id_required(self, session, version_id, id_field):
            captured["version_lookup"] = (version_id, id_field)
            return version

    class NodeRunStore:
        async def list_run_node_runs(self, session, run_id):
            captured["node_run_id"] = run_id
            return [object(), object()]

    class ExecutionService:
        async def execute_existing_run(self, session, **kwargs):
            captured["execution"] = kwargs
            return SimpleNamespace(status="succeeded")

    database_module = ModuleType("app.database")
    database_module.async_session_factory = _SessionContext
    workflow_db_module = ModuleType("app.services.db.workflow_db")
    workflow_db_module.workflow_run_db = RunStore()
    workflow_db_module.workflow_version_db = VersionStore()
    workflow_db_module.node_run_db = NodeRunStore()
    execution_module = ModuleType("app.services.workflow_execution")
    execution_module.workflow_execution_service = ExecutionService()

    monkeypatch.setitem(sys.modules, "app.database", database_module)
    monkeypatch.setitem(sys.modules, "app.services.db.workflow_db", workflow_db_module)
    monkeypatch.setitem(sys.modules, "app.services.workflow_execution", execution_module)

    result = await workflow._execute_workflow_with_real_dependencies(
        run_id="run_1",
        definition={"nodes": [{"id": "untrusted"}]},
        input_data={"text": "untrusted"},
        org_id="untrusted_org",
        agent_id="untrusted_agent",
        actor_user_id="untrusted_user",
    )

    assert result == {"status": "succeeded", "node_count": 2}
    assert captured["run_id"] == "run_1"
    assert captured["version_lookup"] == ("version_1", "version_id")
    assert captured["node_run_id"] == "run_1"
    assert captured["execution"] == {
        "run": run,
        "definition": {"nodes": [{"id": "trusted"}]},
        "input_data": {"text": "trusted"},
        "actor_user_id": "user_1",
    }
