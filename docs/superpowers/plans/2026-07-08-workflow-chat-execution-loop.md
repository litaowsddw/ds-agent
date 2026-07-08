# Workflow Chat Execution Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the second-stage workflow/chat execution loop so Workflow execution has one backend service and users can clearly publish, run, trace, and use workflows from Chat.

**Architecture:** Extract a `WorkflowExecutionService` from `workflow_runs.py` and make Workflow Runs plus Chat workflow mode use it. Keep `packages.workflow.executor.WorkflowExecutor` as the DAG engine, while the API service owns database run creation, node adapters, persistence, and workflow-mode errors. On the frontend, keep existing Zustand stores and Tailwind components, but add state-aware Workflow controls and a Chat context/trace layout.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Pydantic, pytest, Next.js 15, React 19, TypeScript, Zustand, React Flow, Tailwind CSS.

## Global Constraints

- Agent remains usable without Workflow.
- Workflow is optional and belongs to one Agent through `agent_id`.
- Chat autonomous mode remains the default.
- Workflow mode requires a published Workflow, either selected explicitly or configured as Agent default.
- Do not implement Agent automatic routing to Workflow.
- Do not implement all schema-only Workflow nodes.
- Do not introduce a new frontend UI framework or state management library.
- Do not add a database migration for this phase.
- Keep complete node-level audit details in Workflow Runs or Workflow workbench, not inside the Chat message bubble.

---

## File Structure

- Create `apps/api/app/services/workflow_execution.py`: application service for creating, executing, and persisting Workflow Runs.
- Modify `apps/api/app/routes/workflow_runs.py`: remove synchronous node execution details from the route and delegate to `workflow_execution_service`.
- Modify `apps/api/app/routes/chat.py`: share workflow-mode resolution and metadata helpers between normal and SSE chat paths.
- Modify `apps/api/tests/test_chat_workflow_mode.py`: add stream/non-stream metadata parity coverage.
- Create `apps/api/tests/test_workflow_execution_service.py`: service-level success and node error contract tests.
- Modify `apps/web/app/workflows/page.tsx`: add execution state bar, visible disabled reasons, and clearer schema-only node affordances.
- Modify `apps/web/app/chat/page.tsx`: replace duplicate Agent sidebar with a top context bar and Agent selector.
- Modify `apps/web/components/chat/ChatPanel.tsx`: add visible workflow blocked state and extract trace panel out of message bubbles.
- Modify `apps/web/stores/chat.ts`: capture workflow run metadata from SSE events for the trace panel if needed.

---

### Task 1: Extract Workflow Execution Service

**Files:**
- Create: `apps/api/app/services/workflow_execution.py`
- Modify: `apps/api/app/routes/workflow_runs.py`
- Test: `tests/integration/test_e2e_workflow.py`
- Test: `apps/api/tests/test_chat_workflow_mode.py`

**Interfaces:**
- Produces: `workflow_execution_service.create_and_execute(session, *, version_id, input_data, actor_user_id) -> WorkflowRunModel`
- Produces: `workflow_execution_service.execute_existing_run(session, *, run, definition, input_data, actor_user_id) -> WorkflowRunModel`
- Consumes: `workflow_run_db`, `workflow_version_db`, `workflow_db`, `node_run_db`, `membership_db`

- [ ] **Step 1: Create service by moving existing execution helpers**

Create `apps/api/app/services/workflow_execution.py` with the route-local imports and helpers currently used by `apps/api/app/routes/workflow_runs.py`:

```python
"""Workflow execution application service."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_api_key
from app.domain.identity import new_id
from app.gateway.llm import LLMGateway, OpenAICompatibleProvider, llm_gateway
from app.models.runtime import AgentMCPPolicyModel, MCPServerModel, MCPToolModel
from app.models.workflow import WorkflowRunModel
from app.routes.knowledge import search_knowledge_base
from app.schemas.knowledge import SearchRequest
from app.services.db.identity_db import membership_db
from app.services.db.runtime_db import model_provider_db
from app.services.db.workflow_db import (
    knowledge_base_db,
    node_run_db,
    workflow_db,
    workflow_run_db,
    workflow_version_db,
)
from packages.workflow.executor import ExecutedNode, WorkflowExecutor


class WorkflowExecutionService:
    """Create and execute workflow runs with persisted node-level trace."""

    async def create_and_execute(
        self,
        session: AsyncSession,
        *,
        version_id: str,
        input_data: dict[str, Any],
        actor_user_id: str,
    ) -> WorkflowRunModel:
        version = await workflow_version_db.get_by_id_required(session, version_id, "version_id")
        workflow = await workflow_db.get_workflow_required(session, version.workflow_id)
        await membership_db.assert_org_access(session, user_id=actor_user_id, org_id=workflow.org_id)
        run = await workflow_run_db.create_run(
            session,
            run_id=new_id("run"),
            workflow_id=workflow.workflow_id,
            version_id=version.version_id,
            org_id=workflow.org_id,
            agent_id=workflow.agent_id,
            created_by=actor_user_id,
            input_data=input_data,
        )
        await session.flush()
        return await self.execute_existing_run(
            session,
            run=run,
            definition=json.loads(version.definition),
            input_data=input_data,
            actor_user_id=actor_user_id,
        )

    async def execute_existing_run(
        self,
        session: AsyncSession,
        *,
        run: WorkflowRunModel,
        definition: dict[str, Any],
        input_data: dict[str, Any],
        actor_user_id: str,
    ) -> WorkflowRunModel:
        await workflow_run_db.update_run_status(session, run.run_id, "running")
        executor = WorkflowExecutor(
            llm_gateway=lambda config, node_input: self._execute_llm_node(
                session=session,
                config=config,
                node_input=node_input,
                actor_user_id=actor_user_id,
                org_id=run.org_id,
            ),
            rag_search=lambda config, node_input: self._execute_rag_node(
                session=session,
                config=config,
                node_input=node_input,
                actor_user_id=actor_user_id,
                org_id=run.org_id,
            ),
            tool_call=lambda config, node_input: self._execute_tool_node(
                session=session,
                config=config,
                node_input=node_input,
                actor_user_id=actor_user_id,
                org_id=run.org_id,
                agent_id=run.agent_id,
            ),
        )
        result = await executor.execute_async(definition=definition, input_data=input_data)
        for index, executed_node in enumerate(result.node_runs):
            await self._persist_executed_node(session, run.run_id, executed_node, index)
        await workflow_run_db.update_run_status(
            session,
            run.run_id,
            result.status,
            output_data=result.output_data,
            error_message=result.error_message,
        )
        await session.flush()
        return await workflow_run_db.get_run_required(session, run.run_id)

    async def _execute_llm_node(
        self,
        session: AsyncSession,
        config: dict[str, Any],
        node_input: dict[str, Any],
        actor_user_id: str,
        org_id: str,
    ) -> dict[str, Any]:
        provider_key = str(config.get("provider") or "")
        if not provider_key:
            raise ValueError("LLM 节点必须选择真实模型供应商")
        provider_config = await model_provider_db.get_by_key(session, org_id, provider_key)
        if provider_config is None or not provider_config.is_enabled:
            raise ValueError(f"模型供应商未配置或已禁用：{provider_key}")
        gateway = LLMGateway(
            providers={
                provider_key: OpenAICompatibleProvider(
                    base_url=provider_config.base_url,
                    api_key=decrypt_api_key(provider_config.api_key_encrypted),
                    provider_key=provider_key,
                )
            },
            limiter=llm_gateway.limiter,
        )
        enriched_config = {**config, "_org_id": org_id, "_actor_user_id": actor_user_id}
        try:
            return await gateway.generate_from_workflow_node(enriched_config, node_input)
        finally:
            llm_gateway.call_logs.extend(gateway.list_logs())

    async def _execute_rag_node(
        self,
        session: AsyncSession,
        config: dict[str, Any],
        node_input: dict[str, Any],
        actor_user_id: str,
        org_id: str,
    ) -> dict[str, Any]:
        kb_id = str(config.get("kb_id") or "")
        if not kb_id:
            raise ValueError("RAG 节点必须选择知识库")
        kb = await knowledge_base_db.get_by_id_required(session, kb_id, "kb_id")
        if kb.org_id != org_id:
            raise ValueError("RAG 节点不能访问其他组织的知识库")
        query = _render_template(template=str(config.get("query_template") or ""), node_input=node_input)
        if not query:
            query = _stringify_for_query(node_input.get("workflow_input", {}))
        limit = int(config.get("limit") or 5)
        chunks = await search_knowledge_base(
            kb_id=kb_id,
            request=SearchRequest(actor_user_id=actor_user_id, query=query, limit=limit),
            session=session,
        )
        return {
            "kb_id": kb_id,
            "query": query,
            "chunks": [chunk.model_dump() for chunk in chunks],
            "token_estimate": sum(chunk.estimated_tokens for chunk in chunks),
            "upstream": node_input.get("upstream", {}),
        }

    async def _execute_tool_node(
        self,
        session: AsyncSession,
        config: dict[str, Any],
        node_input: dict[str, Any],
        actor_user_id: str,
        org_id: str,
        agent_id: str,
    ) -> dict[str, Any]:
        tool_id = str(config.get("tool_id") or "")
        if not tool_id:
            raise ValueError("Tool 节点必须选择已授权工具")
        arguments = config.get("arguments", {})
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be an object")
        await membership_db.assert_org_access(session, user_id=actor_user_id, org_id=org_id)
        stmt = (
            select(MCPToolModel, MCPServerModel)
            .join(MCPServerModel, MCPToolModel.server_id == MCPServerModel.server_id)
            .join(AgentMCPPolicyModel, AgentMCPPolicyModel.server_id == MCPServerModel.server_id)
            .where(
                AgentMCPPolicyModel.agent_id == agent_id,
                AgentMCPPolicyModel.allowed == True,
                MCPToolModel.tool_id == tool_id,
                MCPServerModel.org_id == org_id,
            )
        )
        result = await session.execute(stmt)
        row = result.first()
        if row is None:
            raise ValueError("Agent 未授权调用该 MCP Tool")
        tool, server = row
        risk_level = str(config.get("risk_level") or tool.risk_level or "low")
        requires_approval = risk_level in {"high", "critical"}
        return {
            "tool_id": tool.tool_id,
            "tool_name": tool.name,
            "server_id": tool.server_id,
            "server_url": server.url,
            "risk_level": risk_level,
            "arguments": arguments,
            "status": "requires_approval" if requires_approval else "planned",
            "requires_approval": requires_approval,
            "upstream": node_input.get("upstream", {}),
        }

    async def _persist_executed_node(
        self,
        session: AsyncSession,
        run_id: str,
        executed_node: ExecutedNode,
        sequence: int,
    ) -> None:
        node_run = await node_run_db.create_node_run(
            session,
            node_run_id=f"{new_id('nr')}_{sequence:04d}",
            run_id=run_id,
            node_id=executed_node.node_id,
            node_type=executed_node.node_type,
            input_data=executed_node.input_data,
        )
        await node_run_db.update_node_run(
            session,
            node_run.node_run_id,
            status=executed_node.status,
            output_data=executed_node.output_data,
            error_message=executed_node.error_message,
            elapsed_ms=executed_node.elapsed_ms,
        )


def _render_template(template: str, node_input: dict[str, Any]) -> str:
    if not template.strip():
        return ""
    workflow_input = node_input.get("workflow_input", {})
    upstream = node_input.get("upstream", {})
    rendered = template
    rendered = rendered.replace("{{input}}", _stringify_for_query(workflow_input))
    rendered = rendered.replace("{{workflow_input}}", _stringify_for_query(workflow_input))
    rendered = rendered.replace("{{upstream}}", _stringify_for_query(upstream))
    return rendered.strip()


def _stringify_for_query(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


workflow_execution_service = WorkflowExecutionService()
```

- [ ] **Step 2: Delegate synchronous route execution to the service**

In `apps/api/app/routes/workflow_runs.py`, import the service:

```python
from app.services.workflow_execution import workflow_execution_service
```

In `create_run`, replace the synchronous create/execute block with:

```python
        if request.async_mode:
            run = await workflow_run_db.create_run(
                session,
                run_id=new_id("run"),
                workflow_id=workflow.workflow_id,
                version_id=version.version_id,
                org_id=workflow.org_id,
                agent_id=workflow.agent_id,
                created_by=request.actor_user_id,
                input_data=request.input_data,
            )
            await session.commit()
            await _submit_async_run(run=run, definition=definition, request=request)
        else:
            run = await workflow_execution_service.create_and_execute(
                session,
                version_id=version.version_id,
                input_data=request.input_data,
                actor_user_id=request.actor_user_id,
            )
            await session.commit()
```

Keep `_submit_async_run`, `_to_run_response`, `_node_run_sequence`, and `_to_node_run_response` in the route. Remove `_execute_run_now`, `_execute_llm_node`, `_execute_rag_node`, `_execute_tool_node`, `_persist_executed_node`, `_render_template`, and `_stringify_for_query` from the route after the service import compiles.

- [ ] **Step 3: Update chat helper import**

In `apps/api/app/routes/workflow_runs.py`, replace `execute_workflow_version_for_chat` with:

```python
async def execute_workflow_version_for_chat(
    session: AsyncSession,
    *,
    version_id: str,
    input_data: dict[str, Any],
    actor_user_id: str,
) -> WorkflowRunModel:
    """创建并同步执行 Workflow Run，供 Chat 流程模式复用。"""

    return await workflow_execution_service.create_and_execute(
        session,
        version_id=version_id,
        input_data=input_data,
        actor_user_id=actor_user_id,
    )
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
pytest tests/integration/test_e2e_workflow.py apps/api/tests/test_chat_workflow_mode.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/workflow_execution.py apps/api/app/routes/workflow_runs.py
git commit -m "refactor: extract workflow execution service"
```

---

### Task 2: Add Workflow Execution Contract Tests

**Files:**
- Create: `apps/api/tests/test_workflow_execution_service.py`
- Modify: `apps/api/app/services/workflow_execution.py`
- Test: `apps/api/tests/test_workflow_execution_service.py`

**Interfaces:**
- Consumes: `workflow_execution_service.create_and_execute(...)`
- Produces: Tool node invalid arguments failure with error text `Tool arguments must be an object`

- [ ] **Step 1: Write contract tests**

Create `apps/api/tests/test_workflow_execution_service.py`:

```python
"""WorkflowExecutionService contract tests."""

from uuid import uuid4

from fastapi.testclient import TestClient

from apps.api.app.main import app


def _suffix(label: str) -> str:
    return f"{label}-{uuid4().hex[:8]}"


def _create_owner_org_agent(client: TestClient, suffix: str) -> tuple[str, str, str]:
    owner_user_id = client.post(
        "/identity/users/register",
        json={"email": f"owner-{suffix}@example.com", "display_name": "Owner", "password": "password123"},
    ).json()["user_id"]
    org_id = client.post(
        "/identity/organizations",
        json={"creator_user_id": owner_user_id, "name": f"Org {suffix}"},
    ).json()["org_id"]
    agent_id = client.post(
        "/agents",
        json={"actor_user_id": owner_user_id, "org_id": org_id, "name": f"Agent {suffix}", "description": ""},
    ).json()["agent_id"]
    return owner_user_id, org_id, agent_id


def _create_and_publish_workflow(
    client: TestClient,
    *,
    actor_user_id: str,
    agent_id: str,
    definition: dict[str, object],
) -> str:
    workflow = client.post(
        "/workflows",
        json={
            "actor_user_id": actor_user_id,
            "agent_id": agent_id,
            "name": "Contract Workflow",
            "description": "",
            "draft_definition": definition,
        },
    ).json()
    publish = client.post(f"/workflows/{workflow['workflow_id']}/publish", json={"actor_user_id": actor_user_id})
    assert publish.status_code == 200
    return publish.json()["version_id"]


def test_workflow_execution_service_persists_node_runs_for_success() -> None:
    with TestClient(app) as client:
        actor_user_id, _org_id, agent_id = _create_owner_org_agent(client, _suffix("wf-service-ok"))
        version_id = _create_and_publish_workflow(
            client,
            actor_user_id=actor_user_id,
            agent_id=agent_id,
            definition={
                "version": "1.0",
                "nodes": [
                    {"id": "start", "type": "start", "config": {}},
                    {"id": "end", "type": "end", "config": {}},
                ],
                "edges": [{"source": "start", "target": "end"}],
            },
        )

        run_response = client.post(
            "/workflow-runs",
            json={
                "actor_user_id": actor_user_id,
                "version_id": version_id,
                "input_data": {"text": "hello"},
                "async_mode": False,
            },
        )

        assert run_response.status_code == 200
        run = run_response.json()
        assert run["status"] == "succeeded"
        node_runs_response = client.get(
            f"/workflow-runs/{run['run_id']}/nodes",
            params={"actor_user_id": actor_user_id},
        )
        assert node_runs_response.status_code == 200
        node_runs = node_runs_response.json()
        assert [node["node_id"] for node in node_runs] == ["start", "end"]
        assert all(node["status"] == "succeeded" for node in node_runs)


def test_tool_arguments_must_be_object() -> None:
    with TestClient(app) as client:
        actor_user_id, _org_id, agent_id = _create_owner_org_agent(client, _suffix("wf-tool-args"))
        version_id = _create_and_publish_workflow(
            client,
            actor_user_id=actor_user_id,
            agent_id=agent_id,
            definition={
                "version": "1.0",
                "nodes": [
                    {"id": "start", "type": "start", "config": {}},
                    {
                        "id": "tool",
                        "type": "tool",
                        "config": {"tool_id": "missing-tool", "arguments": "not-json-object"},
                    },
                    {"id": "end", "type": "end", "config": {}},
                ],
                "edges": [{"source": "start", "target": "tool"}, {"source": "tool", "target": "end"}],
            },
        )

        run_response = client.post(
            "/workflow-runs",
            json={
                "actor_user_id": actor_user_id,
                "version_id": version_id,
                "input_data": {"text": "hello"},
                "async_mode": False,
            },
        )

        assert run_response.status_code == 200
        run = run_response.json()
        assert run["status"] == "failed"
        assert "Tool arguments must be an object" in run["error_message"]
        node_runs = client.get(
            f"/workflow-runs/{run['run_id']}/nodes",
            params={"actor_user_id": actor_user_id},
        ).json()
        failed_tool = next(node for node in node_runs if node["node_id"] == "tool")
        assert failed_tool["status"] == "failed"
        assert "Tool arguments must be an object" in failed_tool["error_message"]
```

- [ ] **Step 2: Run test to verify current behavior**

Run:

```bash
pytest apps/api/tests/test_workflow_execution_service.py -q
```

Expected: PASS after Task 1, including the invalid arguments contract. If the invalid arguments test fails because arguments are still coerced to `{}`, update `WorkflowExecutionService._execute_tool_node` exactly as specified in Task 1.

- [ ] **Step 3: Run related tests**

Run:

```bash
pytest apps/api/tests/test_workflow_execution_service.py tests/integration/test_e2e_workflow.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add apps/api/tests/test_workflow_execution_service.py apps/api/app/services/workflow_execution.py
git commit -m "test: cover workflow execution service contracts"
```

---

### Task 3: Share Chat Workflow Mode Helpers

**Files:**
- Modify: `apps/api/app/routes/chat.py`
- Test: `apps/api/tests/test_chat_workflow_mode.py`

**Interfaces:**
- Produces: `_resolve_workflow_for_chat(db, *, agent, request) -> WorkflowModel`
- Produces: `_workflow_message_metadata(workflow_id: str, workflow_run_id: str) -> dict[str, str]`
- Consumes: `execute_workflow_version_for_chat(...)`

- [ ] **Step 1: Add helper functions to `chat.py`**

In `apps/api/app/routes/chat.py`, below `ChatResponse`, add:

```python
async def _resolve_workflow_for_chat(db: AsyncSession, *, agent: Any, request: ChatRequest) -> Any:
    from apps.api.app.services.db.workflow_db import workflow_db

    workflow_id = request.workflow_id or agent.default_workflow_id or ""
    if not workflow_id:
        raise HTTPException(status_code=400, detail="请选择 Workflow 或改用自主模式")
    workflow = await workflow_db.get_workflow_required(db, workflow_id)
    if workflow.agent_id != request.agent_id:
        raise HTTPException(status_code=400, detail="Workflow 必须属于当前 Agent")
    if workflow.published_version_id is None:
        raise HTTPException(status_code=400, detail="Workflow 必须先发布")
    return workflow


def _workflow_message_metadata(workflow_id: str, workflow_run_id: str) -> dict[str, str]:
    return {
        "execution_mode": "workflow",
        "workflow_id": workflow_id,
        "workflow_run_id": workflow_run_id,
    }
```

- [ ] **Step 2: Use helpers in normal chat workflow path**

In `chat()`, replace the local workflow lookup block with:

```python
            actor_user_id = request.actor_user_id or agent.created_by
            workflow = await _resolve_workflow_for_chat(db, agent=agent, request=request)
```

Replace the assistant `meta_info` object with:

```python
                meta_info=_workflow_message_metadata(workflow.workflow_id, run.run_id),
```

- [ ] **Step 3: Use helpers in stream chat workflow path**

In `_chat_stream_events`, replace the local workflow lookup block with:

```python
            workflow = await _resolve_workflow_for_chat(db, agent=agent, request=request)
```

Replace the assistant `meta_info` object with:

```python
                meta_info=_workflow_message_metadata(workflow.workflow_id, run.run_id),
```

- [ ] **Step 4: Add stream/non-stream parity assertion**

Append this test to `apps/api/tests/test_chat_workflow_mode.py`:

```python
def test_normal_and_stream_workflow_mode_emit_matching_metadata(client: TestClient) -> None:
    suffix = _suffix("chat-parity")
    owner_user_id, org_id, agent_id = _create_owner_org_agent(client, suffix)
    workflow_id = _create_published_passthrough_workflow(client, owner_user_id, agent_id)

    normal_response = client.post(
        "/chat/",
        json={
            "actor_user_id": owner_user_id,
            "agent_id": agent_id,
            "org_id": org_id,
            "message": "normal mode",
            "execution_mode": "workflow",
            "workflow_id": workflow_id,
        },
    )
    assert normal_response.status_code == 200
    normal_body = normal_response.json()

    with client.stream(
        "POST",
        "/chat/stream",
        json={
            "actor_user_id": owner_user_id,
            "agent_id": agent_id,
            "org_id": org_id,
            "message": "stream mode",
            "execution_mode": "workflow",
            "workflow_id": workflow_id,
        },
    ) as response:
        assert response.status_code == 200
        stream_body = "".join(response.iter_text())
    events = _parse_sse_events(stream_body)
    stream_finished = next(event for event in events if event["event"] == "run_finished")

    assert normal_body["mode"] == stream_finished["mode"] == "workflow"
    assert normal_body["workflow_id"] == stream_finished["workflow_id"] == workflow_id
    assert normal_body["workflow_run_id"]
    assert stream_finished["workflow_run_id"]
```

- [ ] **Step 5: Run tests**

Run:

```bash
pytest apps/api/tests/test_chat_workflow_mode.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/routes/chat.py apps/api/tests/test_chat_workflow_mode.py
git commit -m "refactor: share chat workflow mode helpers"
```

---

### Task 4: Improve Workflow Workbench State Flow

**Files:**
- Modify: `apps/web/app/workflows/page.tsx`
- Test: `apps/web` TypeScript build

**Interfaces:**
- Consumes: `selectedAgentId`, `selectedWorkflow`, `runs`, `nodeRuns`
- Produces: local UI helpers `WorkflowProgress`, `ActionHint`, `workflowCanRun`, `schemaNodeCount`

- [ ] **Step 1: Add derived state in WorkflowsPage**

In `apps/web/app/workflows/page.tsx`, after `paletteGroups`, add:

```tsx
  const latestRun = runs.find((run) => run.workflow_id === selectedWorkflowId);
  const schemaNodeCount = nodes.filter((node) => node.data.capability === "schema").length;
  const hasWorkflow = Boolean(selectedWorkflowId && selectedWorkflow);
  const isPublished = Boolean(selectedWorkflow?.published_version_id);
  const workflowCanRun = hasWorkflow && isPublished;
  const runDisabledReason = !hasWorkflow
    ? "Create or select a workflow first"
    : !isPublished
      ? "Publish the workflow before running it"
      : "";
```

- [ ] **Step 2: Add progress bar under the canvas header**

In the canvas header block, below the subtitle, render:

```tsx
            <WorkflowProgress
              hasAgent={Boolean(selectedAgentId)}
              hasWorkflow={hasWorkflow}
              isPublished={isPublished}
              hasRun={Boolean(latestRun)}
            />
```

Add this component near `ActionButton`:

```tsx
function WorkflowProgress({
  hasAgent,
  hasWorkflow,
  isPublished,
  hasRun,
}: {
  hasAgent: boolean;
  hasWorkflow: boolean;
  isPublished: boolean;
  hasRun: boolean;
}) {
  const steps = [
    { label: "Agent selected", done: hasAgent },
    { label: "Draft saved", done: hasWorkflow },
    { label: "Published", done: isPublished },
    { label: "Run complete", done: hasRun },
  ];
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {steps.map((step) => (
        <span
          key={step.label}
          className={`rounded px-2 py-1 text-[11px] font-medium ${
            step.done ? "bg-[#ecfdf3] text-[#027a48]" : "bg-[#f8fafc] text-[#667085]"
          }`}
        >
          {step.label}
        </span>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Add visible action hints and disabled run state**

Replace the Run `ActionButton` with a native button that supports `disabled`:

```tsx
              <ActionButton icon={<Save size={14} />} label="Save" onClick={() => void saveWorkflowDraft(workspace.userId).then(() => showToast("success", "Draft saved")).catch((error) => showToast("error", error instanceof Error ? error.message : "Save failed"))} />
              <ActionButton icon={<Send size={14} />} label="Publish" onClick={() => void publishWorkflow(workspace.userId).then(() => showToast("success", "Published")).catch((error) => showToast("error", error instanceof Error ? error.message : "Publish failed"))} />
              <ActionButton
                disabled={!workflowCanRun}
                icon={<Play size={14} />}
                label="Run"
                onClick={() => void runWorkflow(workspace.userId, workflowForm.input).then(() => showToast("success", "Run complete")).catch((error) => showToast("error", error instanceof Error ? error.message : "Run failed"))}
                title={runDisabledReason || undefined}
              />
```

Update `ActionButton` signature:

```tsx
function ActionButton({
  disabled = false,
  icon,
  label,
  onClick,
  title,
}: {
  disabled?: boolean;
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  title?: string;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      title={title}
      className="inline-flex items-center justify-center gap-1 rounded-lg border border-[#cfd7e6] bg-white px-2 py-2 text-xs font-medium text-[#172033] transition hover:border-[#2f6feb] disabled:cursor-not-allowed disabled:opacity-50"
    >
      {icon}
      {label}
    </button>
  );
}
```

Below the action button grid, add:

```tsx
            {runDisabledReason ? <ActionHint text={runDisabledReason} /> : null}
            {schemaNodeCount > 0 ? (
              <ActionHint text={`${schemaNodeCount} schema-only node${schemaNodeCount > 1 ? "s are" : " is"} design-only in this phase.`} />
            ) : null}
```

Add:

```tsx
function ActionHint({ text }: { text: string }) {
  return <div className="rounded-lg bg-[#f8fafc] px-3 py-2 text-xs text-[#667085]">{text}</div>;
}
```

- [ ] **Step 4: Clarify schema-only palette copy**

In the node palette card, replace the description line with:

```tsx
                    <div className="mt-1 text-xs leading-5 text-[#667085]">
                      {item.description}
                      {item.capability === "schema" ? " 可设计，暂不参与真实执行。" : ""}
                    </div>
```

- [ ] **Step 5: Run frontend build**

Run from `apps/web`:

```bash
npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/web/app/workflows/page.tsx
git commit -m "feat: clarify workflow workbench execution state"
```

---

### Task 5: Simplify Chat Context and Trace UI

**Files:**
- Modify: `apps/web/app/chat/page.tsx`
- Modify: `apps/web/components/chat/ChatPanel.tsx`
- Modify: `apps/web/stores/chat.ts`
- Test: `apps/web` TypeScript build

**Interfaces:**
- Consumes: `agents`, `selectedAgentId`, `setSelectedAgentId`, `workflows`
- Produces: visible workflow blocked message and standalone `ThinkingTrace`

- [ ] **Step 1: Replace duplicate Agent sidebar with context bar**

In `apps/web/app/chat/page.tsx`, replace the outer layout with this structure:

```tsx
  return (
    <div className="flex h-full min-h-0 flex-col bg-[#f7f8fa]">
      <div className="border-b border-[#dfe4ee] bg-white px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-[#172033]">Agent Runtime</div>
            <div className="mt-1 text-xs text-[#667085]">
              {selectedAgent ? selectedAgent.name : "Select an Agent"} · {workflows.length} workflows
            </div>
          </div>
          <select
            className="h-9 min-w-[220px] rounded-lg border border-[#dfe4ee] bg-white px-3 text-sm text-[#172033]"
            onChange={(event) => setSelectedAgentId(event.target.value)}
            value={agentId}
          >
            <option value="">Select an Agent</option>
            {agents?.map((agent) => (
              <option key={agent.agent_id} value={agent.agent_id}>
                {agent.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex border-b border-[#dfe4ee] bg-white px-4">
        ...
      </div>

      <div className="min-h-0 flex-1 overflow-hidden">
        ...
      </div>
    </div>
  );
```

Keep the existing Chat / Skill Evolver tab buttons inside the second bar, but switch their active classes to `text-[#2f6feb] border-b-2 border-[#2f6feb]`.

- [ ] **Step 2: Move trace out of message bubble**

In `apps/web/components/chat/ChatPanel.tsx`, remove:

```tsx
                {msg.message_id === lastAssistantId && shouldShowThinking ? <ThinkingTrace events={traceEvents} /> : null}
```

Remove the `lastAssistantId` constant if unused. Above the input controls, add:

```tsx
          {traceEvents.length > 0 ? <ThinkingTrace events={traceEvents} /> : null}
```

- [ ] **Step 3: Make blocked workflow state visible**

In `ChatPanel`, below the workflow selector block, add:

```tsx
            {workflowModeBlockedReason ? (
              <div className="basis-full rounded-lg bg-[#fff7ed] px-3 py-2 text-xs text-[#9a3412]">
                当前 Agent 还没有可用的已发布 Workflow。请先到{" "}
                <a className="font-medium text-[#2f6feb] underline" href="/workflows">
                  Workflows
                </a>{" "}
                发布流程，或切回自主模式。
              </div>
            ) : null}
```

Change the autonomous/workflow segmented control classes from `blue-500/gray/dark` to the app palette:

```tsx
                className={`rounded-md px-3 py-1.5 ${executionMode === "autonomous" ? "bg-[#2f6feb] text-white" : "text-[#667085]"}`}
```

and:

```tsx
                className={`rounded-md px-3 py-1.5 ${executionMode === "workflow" ? "bg-[#2f6feb] text-white" : "text-[#667085]"}`}
```

- [ ] **Step 4: Add workflow run detail to trace**

In `renderTraceDetail`, before the final `detail` line, add:

```tsx
  const workflowRunId = typeof event.data.workflow_run_id === "string" ? event.data.workflow_run_id : "";
  if (workflowRunId) {
    return <div className="mt-0.5 truncate text-[#667085]">Run {workflowRunId}</div>;
  }
```

In `ThinkingTrace`, update the wrapper classes to app palette:

```tsx
    <div className="mb-3 rounded-lg border border-[#dfe4ee] bg-[#f8fafc] px-3 py-2 text-xs">
```

- [ ] **Step 5: Run frontend build**

Run from `apps/web`:

```bash
npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/web/app/chat/page.tsx apps/web/components/chat/ChatPanel.tsx apps/web/stores/chat.ts
git commit -m "feat: clarify chat workflow context"
```

---

### Task 6: Final Verification

**Files:**
- Verify only.

**Interfaces:**
- Consumes all earlier tasks.
- Produces verified local implementation.

- [ ] **Step 1: Run backend focused tests**

Run:

```bash
pytest apps/api/tests/test_workflow_execution_service.py apps/api/tests/test_chat_workflow_mode.py tests/integration/test_e2e_workflow.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run from `apps/web`:

```bash
npm run build
```

Expected: PASS.

- [ ] **Step 3: Inspect git status**

Run:

```bash
git status --short
```

Expected: no uncommitted changes.

- [ ] **Step 4: Commit only if verification required fixes**

If verification required fixes, commit them:

```bash
git add <fixed-files>
git commit -m "fix: stabilize workflow chat execution loop"
```

If no files changed, do not create an empty commit.

---

## Self-Review

Spec coverage:

- One backend execution source: Tasks 1 and 2.
- Chat workflow metadata parity: Task 3.
- Workflow workbench state flow: Task 4.
- Chat context, visible blocked state, and separate trace: Task 5.
- Verification: Task 6.

Placeholder scan:

- No task uses unresolved placeholder wording or undefined file names.
- Each code-changing task names exact files, concrete snippets, commands, and expected results.

Type consistency:

- Service method names are consistently `create_and_execute` and `execute_existing_run`.
- Workflow metadata keys are consistently `execution_mode`, `workflow_id`, and `workflow_run_id`.
- Frontend execution mode remains `ChatExecutionMode = "autonomous" | "workflow"`.
