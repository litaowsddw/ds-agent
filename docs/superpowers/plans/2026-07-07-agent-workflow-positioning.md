# Agent Workflow Positioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved MVP where Agent is the primary product surface and Workflow is an optional execution strategy for stable Agent task flows.

**Architecture:** Keep existing Agent Runtime and WorkflowExecutor boundaries, but add a thin execution-mode contract at the Chat API and UI. Store an optional default Workflow reference on Agent, filter Workflows by selected Agent, and reuse Workflow Run persistence for workflow-mode chat.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Pydantic, pytest, Next.js 15, React 19, TypeScript, Zustand, React Flow, Tailwind CSS.

## Global Constraints

- Agent remains usable without Workflow.
- Workflow is optional and belongs to one Agent through `agent_id`.
- First phase does not implement automatic Agent routing to Workflow.
- First phase does not implement all schema-only Workflow nodes.
- Do not introduce a new frontend UI framework or state management library.
- Chat autonomous mode is the default.
- Workflow mode requires a published Workflow, either selected explicitly or configured as Agent default.

---

## File Structure

- `apps/api/app/models/agent.py`: add `default_workflow_id` to `AgentModel`.
- `apps/api/app/schemas/agent.py`: expose `default_workflow_id` in create, update, and response schemas.
- `apps/api/app/services/db/agent_db.py`: persist `default_workflow_id` during create/update.
- `apps/api/app/routes/agents.py`: validate default Workflow ownership and published status before saving.
- `apps/api/app/routes/chat.py`: add execution-mode schema fields and route workflow-mode chat to Workflow Run execution.
- `apps/api/app/routes/workflow_runs.py`: expose a focused helper that runs an existing Workflow Version in-process for reuse by Chat.
- `apps/api/tests/test_agents_api.py`: cover default Workflow behavior.
- `apps/api/tests/test_chat_workflow_mode.py`: cover autonomous default, workflow mode, and cross-Agent rejection.
- `apps/web/types/agent.ts`: add `default_workflow_id`.
- `apps/web/types/workflow.ts`: confirm Workflow published metadata is usable by Chat selectors.
- `apps/web/stores/workflow.ts`: support `agentId` filtering for Workflow refresh.
- `apps/web/stores/workspace.ts`: include default Workflow in create/update calls and Agent type state.
- `apps/web/stores/chat.ts`: add execution mode and Workflow ID to `sendMessage` and SSE payload.
- `apps/web/app/agents/page.tsx`: add Agent Workflow strategy section and default Workflow save control.
- `apps/web/app/workflows/page.tsx`: filter current Agent Workflows and improve Agent-centered copy.
- `apps/web/app/chat/page.tsx`: load current Agent Workflows and pass them to `ChatPanel`.
- `apps/web/components/chat/ChatPanel.tsx`: add autonomous/workflow segmented control and Workflow selector.
- `README.md`, `docs/CURRENT_STATUS.md`, `docs/DEVELOPMENT_PLAN.md`, `docs/PROJECT_STRUCTURE.md`: update project positioning.

---

### Task 1: Agent Default Workflow Contract

**Files:**
- Modify: `apps/api/app/models/agent.py`
- Modify: `apps/api/app/schemas/agent.py`
- Modify: `apps/api/app/services/db/agent_db.py`
- Modify: `apps/api/app/routes/agents.py`
- Test: `apps/api/tests/test_agents_api.py`

**Interfaces:**
- Consumes: existing `workflow_db.get_workflow_required(session, workflow_id)`.
- Produces: `AgentResponse.default_workflow_id: str | None`.
- Produces: `AgentCreateRequest.default_workflow_id: str | None`.
- Produces: `AgentUpdateRequest.default_workflow_id: str | None`.

- [ ] **Step 1: Write failing API tests**

Append these tests to `apps/api/tests/test_agents_api.py`:

```python
def test_agent_default_workflow_starts_empty() -> None:
    client = TestClient(app)
    suffix = "agent-default-workflow-empty"
    owner_response = client.post(
        "/identity/users/register",
        json={"email": f"owner-{suffix}@example.com", "display_name": "Owner", "password": "password123"},
    )
    owner_user_id = owner_response.json()["user_id"]
    org_response = client.post(
        "/identity/organizations",
        json={"creator_user_id": owner_user_id, "name": "Default Workflow Org"},
    )
    org_id = org_response.json()["org_id"]

    agent_response = client.post(
        "/agents",
        json={"actor_user_id": owner_user_id, "org_id": org_id, "name": "Autonomous Agent", "description": ""},
    )

    assert agent_response.status_code == 200
    assert agent_response.json()["default_workflow_id"] is None


def test_agent_update_rejects_default_workflow_from_other_agent() -> None:
    client = TestClient(app)
    suffix = "agent-default-workflow-cross"
    owner_response = client.post(
        "/identity/users/register",
        json={"email": f"owner-{suffix}@example.com", "display_name": "Owner", "password": "password123"},
    )
    owner_user_id = owner_response.json()["user_id"]
    org_id = client.post(
        "/identity/organizations",
        json={"creator_user_id": owner_user_id, "name": "Cross Workflow Org"},
    ).json()["org_id"]
    agent_a = client.post(
        "/agents",
        json={"actor_user_id": owner_user_id, "org_id": org_id, "name": "Agent A", "description": ""},
    ).json()
    agent_b = client.post(
        "/agents",
        json={"actor_user_id": owner_user_id, "org_id": org_id, "name": "Agent B", "description": ""},
    ).json()
    workflow = client.post(
        "/workflows",
        json={
            "actor_user_id": owner_user_id,
            "agent_id": agent_b["agent_id"],
            "name": "Agent B Workflow",
            "description": "",
            "draft_definition": {
                "version": "1.0",
                "nodes": [{"id": "start", "type": "start", "config": {}}, {"id": "end", "type": "end", "config": {}}],
                "edges": [{"source": "start", "target": "end"}],
            },
        },
    ).json()
    client.post(f"/workflows/{workflow['workflow_id']}/publish", json={"actor_user_id": owner_user_id})

    update_response = client.put(
        f"/agents/{agent_a['agent_id']}",
        json={
            "actor_user_id": owner_user_id,
            "name": "Agent A",
            "description": "",
            "default_workflow_id": workflow["workflow_id"],
        },
    )

    assert update_response.status_code == 400
    assert "默认 Workflow 必须属于当前 Agent" in update_response.text


def test_agent_update_accepts_own_published_default_workflow() -> None:
    client = TestClient(app)
    suffix = "agent-default-workflow-own"
    owner_response = client.post(
        "/identity/users/register",
        json={"email": f"owner-{suffix}@example.com", "display_name": "Owner", "password": "password123"},
    )
    owner_user_id = owner_response.json()["user_id"]
    org_id = client.post(
        "/identity/organizations",
        json={"creator_user_id": owner_user_id, "name": "Own Workflow Org"},
    ).json()["org_id"]
    agent = client.post(
        "/agents",
        json={"actor_user_id": owner_user_id, "org_id": org_id, "name": "Agent", "description": ""},
    ).json()
    workflow = client.post(
        "/workflows",
        json={
            "actor_user_id": owner_user_id,
            "agent_id": agent["agent_id"],
            "name": "Default Workflow",
            "description": "",
            "draft_definition": {
                "version": "1.0",
                "nodes": [{"id": "start", "type": "start", "config": {}}, {"id": "end", "type": "end", "config": {}}],
                "edges": [{"source": "start", "target": "end"}],
            },
        },
    ).json()
    client.post(f"/workflows/{workflow['workflow_id']}/publish", json={"actor_user_id": owner_user_id})

    update_response = client.put(
        f"/agents/{agent['agent_id']}",
        json={
            "actor_user_id": owner_user_id,
            "name": "Agent",
            "description": "",
            "default_workflow_id": workflow["workflow_id"],
        },
    )

    assert update_response.status_code == 200
    assert update_response.json()["default_workflow_id"] == workflow["workflow_id"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest apps/api/tests/test_agents_api.py -q
```

Expected: FAIL because `default_workflow_id` is not in `AgentResponse` and update validation is missing.

- [ ] **Step 3: Add ORM and schema field**

In `apps/api/app/models/agent.py`, add this column after `max_tokens`:

```python
    default_workflow_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
```

In `apps/api/app/schemas/agent.py`, add this field to `AgentCreateRequest`, `AgentUpdateRequest`, and `AgentResponse`:

```python
    default_workflow_id: str | None = Field(default=None, description="默认 Workflow ID，空值表示自主模式")
```

For `AgentResponse`, use:

```python
    default_workflow_id: str | None = None
```

- [ ] **Step 4: Persist and return default Workflow**

In `apps/api/app/services/db/agent_db.py`, add a parameter to `create_agent`:

```python
        default_workflow_id: str | None = None,
```

Set it on `AgentModel(...)`:

```python
            default_workflow_id=default_workflow_id,
```

In `apps/api/app/routes/agents.py`, pass create request value:

```python
            default_workflow_id=request.default_workflow_id,
```

In `_to_agent_response`, include:

```python
        default_workflow_id=agent.default_workflow_id,
```

- [ ] **Step 5: Validate default Workflow ownership and publication**

In `apps/api/app/routes/agents.py`, import `workflow_db`:

```python
from app.services.db.workflow_db import workflow_db
```

Add this helper above `_to_agent_response`:

```python
async def _validate_default_workflow(
    session: AsyncSession,
    agent: AgentModel,
    default_workflow_id: str | None,
) -> None:
    """校验默认 Workflow 属于当前 Agent 且已发布。"""

    if not default_workflow_id:
        return
    workflow = await workflow_db.get_workflow_required(session, default_workflow_id)
    if workflow.agent_id != agent.agent_id:
        raise ValueError("默认 Workflow 必须属于当前 Agent")
    if workflow.published_version_id is None:
        raise ValueError("默认 Workflow 必须先发布")
```

In `update_agent`, after org access and before update:

```python
        if "default_workflow_id" in update_data:
            await _validate_default_workflow(session, agent, update_data["default_workflow_id"])
```

In `create_agent`, immediately after `agent = await agent_db.create_agent(...)`:

```python
        await _validate_default_workflow(session, agent, request.default_workflow_id)
```

- [ ] **Step 6: Run tests to verify pass**

Run:

```bash
pytest apps/api/tests/test_agents_api.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/models/agent.py apps/api/app/schemas/agent.py apps/api/app/services/db/agent_db.py apps/api/app/routes/agents.py apps/api/tests/test_agents_api.py
git commit -m "feat: add agent default workflow contract"
```

---

### Task 2: Reusable Workflow Execution for Chat

**Files:**
- Modify: `apps/api/app/routes/workflow_runs.py`
- Modify: `apps/api/app/routes/chat.py`
- Test: `apps/api/tests/test_chat_workflow_mode.py`

**Interfaces:**
- Consumes: `WorkflowRunCreateRequest`.
- Produces: `execute_workflow_version_for_chat(session, *, version_id, input_data, actor_user_id) -> WorkflowRunModel`.
- Produces: `ChatRequest.execution_mode: Literal["autonomous", "workflow"]`.
- Produces: `ChatRequest.workflow_id: str | None`.

- [ ] **Step 1: Write failing chat workflow tests**

Create `apps/api/tests/test_chat_workflow_mode.py`:

```python
"""Chat workflow execution mode tests."""

from fastapi.testclient import TestClient

from apps.api.app.main import app


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


def _create_published_passthrough_workflow(client: TestClient, owner_user_id: str, agent_id: str) -> str:
    workflow = client.post(
        "/workflows",
        json={
            "actor_user_id": owner_user_id,
            "agent_id": agent_id,
            "name": "Passthrough",
            "description": "",
            "draft_definition": {
                "version": "1.0",
                "nodes": [{"id": "start", "type": "start", "config": {}}, {"id": "end", "type": "end", "config": {}}],
                "edges": [{"source": "start", "target": "end"}],
            },
        },
    ).json()
    publish = client.post(f"/workflows/{workflow['workflow_id']}/publish", json={"actor_user_id": owner_user_id})
    assert publish.status_code == 200
    return workflow["workflow_id"]


def test_chat_workflow_mode_executes_published_workflow_and_saves_session() -> None:
    client = TestClient(app)
    owner_user_id, org_id, agent_id = _create_owner_org_agent(client, "chat-workflow")
    workflow_id = _create_published_passthrough_workflow(client, owner_user_id, agent_id)

    response = client.post(
        "/chat/",
        json={
            "actor_user_id": owner_user_id,
            "agent_id": agent_id,
            "org_id": org_id,
            "message": "稳定输入",
            "execution_mode": "workflow",
            "workflow_id": workflow_id,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "workflow"
    assert body["workflow_id"] == workflow_id
    assert body["workflow_run_id"]
    assert "稳定输入" in body["response"]

    messages = client.get(f"/chat/sessions/{body['session_id']}/messages").json()["messages"]
    assert [message["role"] for message in messages][-2:] == ["user", "assistant"]


def test_chat_workflow_mode_rejects_cross_agent_workflow() -> None:
    client = TestClient(app)
    owner_user_id, org_id, agent_a = _create_owner_org_agent(client, "chat-cross-a")
    _, _, agent_b = _create_owner_org_agent(client, "chat-cross-b")
    workflow_id = _create_published_passthrough_workflow(client, owner_user_id, agent_b)

    response = client.post(
        "/chat/",
        json={
            "actor_user_id": owner_user_id,
            "agent_id": agent_a,
            "org_id": org_id,
            "message": "try cross",
            "execution_mode": "workflow",
            "workflow_id": workflow_id,
        },
    )

    assert response.status_code == 400
    assert "Workflow 必须属于当前 Agent" in response.text
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest apps/api/tests/test_chat_workflow_mode.py -q
```

Expected: FAIL because Chat schema has no `execution_mode`/`workflow_id` and no workflow-mode path.

- [ ] **Step 3: Extract reusable Workflow Run helper**

In `apps/api/app/routes/workflow_runs.py`, add this function below `create_run`:

```python
async def execute_workflow_version_for_chat(
    session: AsyncSession,
    *,
    version_id: str,
    input_data: dict[str, Any],
    actor_user_id: str,
) -> WorkflowRunModel:
    """创建并同步执行 Workflow Run，供 Chat 流程模式复用。"""

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
    await _execute_run_now(
        session=session,
        run=run,
        definition=json.loads(version.definition),
        input_data=input_data,
        actor_user_id=actor_user_id,
    )
    await session.flush()
    return await workflow_run_db.get_run_required(session, run.run_id)
```

In `create_run`, replace duplicate create/execute logic only if it stays readable. The safe first pass is to leave `create_run` unchanged and reuse the helper only from Chat.

- [ ] **Step 4: Extend Chat schemas**

In `apps/api/app/routes/chat.py`, import `Literal`:

```python
from typing import AsyncIterator, Literal
```

Add fields to `ChatRequest`:

```python
    execution_mode: Literal["autonomous", "workflow"] = "autonomous"
    workflow_id: str | None = None
```

Add fields to `ChatResponse`:

```python
    workflow_id: str = ""
    workflow_run_id: str = ""
```

- [ ] **Step 5: Implement workflow-mode chat path**

In `chat()` in `apps/api/app/routes/chat.py`, after loading and validating `agent`, before model-provider validation, insert:

```python
        if request.execution_mode == "workflow":
            from apps.api.app.routes.workflow_runs import execute_workflow_version_for_chat
            from apps.api.app.services.db.workflow_db import workflow_db

            workflow_id = request.workflow_id or agent.default_workflow_id or ""
            if not workflow_id:
                raise HTTPException(status_code=400, detail="请选择 Workflow 或改用自主模式")
            workflow = await workflow_db.get_workflow_required(db, workflow_id)
            if workflow.agent_id != request.agent_id:
                raise HTTPException(status_code=400, detail="Workflow 必须属于当前 Agent")
            if workflow.published_version_id is None:
                raise HTTPException(status_code=400, detail="Workflow 必须先发布")

            run = await execute_workflow_version_for_chat(
                db,
                version_id=workflow.published_version_id,
                input_data={"text": request.message},
                actor_user_id=request.actor_user_id or agent.created_by,
            )
            response_text = json.dumps(json.loads(run.output_data), ensure_ascii=False, sort_keys=True)
            await session_message_db.append_message(
                db,
                message_id=new_id("msg"),
                session_id=session_id,
                org_id=request.org_id,
                agent_id=request.agent_id,
                role="assistant",
                content=response_text,
                estimated_tokens=max(1, len(response_text) // 4),
            )
            await db.commit()
            return ChatResponse(
                response=response_text,
                agent_id=request.agent_id,
                session_id=session_id,
                mode="workflow",
                workflow_id=workflow.workflow_id,
                workflow_run_id=run.run_id,
            )
```

Add `import json` at the top of `chat.py`.

- [ ] **Step 6: Run backend tests**

Run:

```bash
pytest apps/api/tests/test_chat_workflow_mode.py apps/api/tests/test_agents_api.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/routes/workflow_runs.py apps/api/app/routes/chat.py apps/api/tests/test_chat_workflow_mode.py
git commit -m "feat: run workflows from chat mode"
```

---

### Task 3: Workflow Store Agent Filtering

**Files:**
- Modify: `apps/web/stores/workflow.ts`
- Modify: `apps/web/types/workflow.ts`
- Test: `apps/web` TypeScript build

**Interfaces:**
- Consumes: backend `GET /workflows?org_id=&actor_user_id=&agent_id=`.
- Produces: `refreshWorkflows(orgId: string, actorUserId: string, agentId?: string) => Promise<void>`.
- Produces: `publishedWorkflowsForAgent(agentId: string): WorkflowItem[]` if needed by Chat page.

- [ ] **Step 1: Update `refreshWorkflows` signature**

In `apps/web/stores/workflow.ts`, change the interface entry:

```ts
  refreshWorkflows: (orgId: string, actorUserId: string, agentId?: string) => Promise<void>;
```

Change the implementation:

```ts
  refreshWorkflows: async (orgId, actorUserId, agentId) => {
    const params = new URLSearchParams({ org_id: orgId, actor_user_id: actorUserId });
    if (agentId) params.set("agent_id", agentId);
    const workflows = await apiRequest<WorkflowItem[]>(`/workflows?${params.toString()}`);
    set((state) => {
      const selectedWorkflowId =
        workflows.some((item) => item.workflow_id === state.selectedWorkflowId)
          ? state.selectedWorkflowId
          : workflows[0]?.workflow_id || "";
      const selectedWorkflow = workflows.find((item) => item.workflow_id === selectedWorkflowId);
      const nodes = selectedWorkflow ? hydrateNodes(selectedWorkflow.draft_definition) : state.nodes;
      return {
        workflows,
        selectedWorkflowId,
        nodes,
        edges: selectedWorkflow ? hydrateEdges(selectedWorkflow.draft_definition) : state.edges,
        selectedNodeId: nodes.find((node) => node.type !== "start")?.id ?? nodes[0]?.id ?? "",
      };
    });
  },
```

- [ ] **Step 2: Run TypeScript check**

Run:

```bash
npm run build
```

from `apps/web`.

Expected: FAIL with call sites that still pass two arguments or other type errors.

- [ ] **Step 3: Update Workflows page call site**

In `apps/web/app/workflows/page.tsx`, change:

```ts
    void refreshWorkflows(workspace.orgId, workspace.userId);
```

to:

```ts
    void refreshWorkflows(workspace.orgId, workspace.userId, selectedAgentId || undefined);
```

- [ ] **Step 4: Run TypeScript build**

Run:

```bash
npm run build
```

from `apps/web`.

Expected: PASS or only pre-existing unrelated Next.js/lint warnings. If it fails, fix the exact compile errors from this task.

- [ ] **Step 5: Commit**

```bash
git add apps/web/stores/workflow.ts apps/web/app/workflows/page.tsx apps/web/types/workflow.ts
git commit -m "feat: filter workflows by selected agent"
```

---

### Task 4: Agent Workspace Workflow Strategy UI

**Files:**
- Modify: `apps/web/types/agent.ts`
- Modify: `apps/web/stores/workspace.ts`
- Modify: `apps/web/app/agents/page.tsx`
- Test: `apps/web` TypeScript build

**Interfaces:**
- Consumes: `Agent.default_workflow_id`.
- Consumes: `useWorkflowStore.refreshWorkflows(orgId, userId, agentId)`.
- Produces: Agent update payload with `default_workflow_id`.

- [ ] **Step 1: Add frontend Agent type field**

In `apps/web/types/agent.ts`, add to `Agent`:

```ts
  /** 默认 Workflow，空值表示自主模式 */
  default_workflow_id?: string | null;
```

Add to `CreateAgentRequest`:

```ts
  default_workflow_id?: string | null;
```

- [ ] **Step 2: Add store update parameter**

In `apps/web/stores/workspace.ts`, add `defaultWorkflowId?: string | null;` to `createAgent` and `updateAgent` form types.

Add to create body:

```ts
          default_workflow_id: form.defaultWorkflowId ?? null,
```

Add to update body:

```ts
          default_workflow_id: form.defaultWorkflowId ?? null,
```

- [ ] **Step 3: Load current Agent Workflows on Agents page**

In `apps/web/app/agents/page.tsx`, import workflow store:

```ts
import { useWorkflowStore } from "@/stores/workflow";
```

Inside `AgentsPage`, add:

```ts
  const workflows = useWorkflowStore((state) => state.workflows);
  const refreshWorkflows = useWorkflowStore((state) => state.refreshWorkflows);
```

In the selected-agent effect, add:

```ts
    void refreshWorkflows(workspace.orgId, workspace.userId, selectedAgentId);
```

- [ ] **Step 4: Add default Workflow state and save payload**

In `parameterForm`, add:

```ts
    defaultWorkflowId: "",
```

In the selected-agent hydration, set:

```ts
      defaultWorkflowId: selectedAgent.default_workflow_id ?? "",
```

In empty reset, set:

```ts
        defaultWorkflowId: "",
```

In `updateAgent(...)` payload, add:

```ts
                      defaultWorkflowId: parameterForm.defaultWorkflowId || null,
```

- [ ] **Step 5: Render Workflow strategy panel**

In `apps/web/app/agents/page.tsx`, after the "Agent 参数" panel and before "Agent Workspace", add:

```tsx
        <Panel title="Workflow 策略" icon={<Network size={17} />}>
          {selectedAgent ? (
            <div className="space-y-3">
              <div className="grid gap-2 sm:grid-cols-3">
                <Metric label="Workflows" value={workflows.length} />
                <Metric label="Published" value={workflows.filter((workflow) => workflow.published_version_id).length} />
                <Metric label="Mode" value={parameterForm.defaultWorkflowId ? "流程" : "自主"} />
              </div>
              <SelectInput
                label="默认 Workflow"
                value={parameterForm.defaultWorkflowId}
                onChange={(defaultWorkflowId) => setParameterForm({ ...parameterForm, defaultWorkflowId })}
                options={[
                  { label: "不设置默认流程，使用自主模式", value: "" },
                  ...workflows
                    .filter((workflow) => workflow.published_version_id)
                    .map((workflow) => ({ label: workflow.name, value: workflow.workflow_id })),
                ]}
              />
              <div className="space-y-2">
                {workflows.length === 0 ? <EmptyText text="当前 Agent 暂无 Workflow" /> : null}
                {workflows.slice(0, 5).map((workflow) => (
                  <div key={workflow.workflow_id} className="rounded-lg border border-[#dfe4ee] bg-white px-3 py-2 text-sm">
                    <div className="font-medium text-[#172033]">{workflow.name}</div>
                    <div className="mt-1 text-xs text-[#667085]">
                      {workflow.published_version_id ? "已发布" : "草稿"}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <EmptyText text="请选择 Agent 后配置 Workflow 策略" />
          )}
        </Panel>
```

- [ ] **Step 6: Run TypeScript build**

Run:

```bash
npm run build
```

from `apps/web`.

Expected: PASS. If it fails because `parameterForm` object literals are missing `defaultWorkflowId`, update every reset object to include it.

- [ ] **Step 7: Commit**

```bash
git add apps/web/types/agent.ts apps/web/stores/workspace.ts apps/web/app/agents/page.tsx
git commit -m "feat: show agent workflow strategy"
```

---

### Task 5: Chat Execution Mode UI

**Files:**
- Modify: `apps/web/stores/chat.ts`
- Modify: `apps/web/app/chat/page.tsx`
- Modify: `apps/web/components/chat/ChatPanel.tsx`
- Test: `apps/web` TypeScript build

**Interfaces:**
- Consumes: `WorkflowItem[]`.
- Produces: `sendMessage(agentId, orgId, message, actorUserId, options?)`.
- Produces: SSE payload fields `execution_mode` and `workflow_id`.

- [ ] **Step 1: Add chat send options type**

In `apps/web/stores/chat.ts`, add:

```ts
export type ChatExecutionMode = "autonomous" | "workflow";

export interface SendMessageOptions {
  executionMode?: ChatExecutionMode;
  workflowId?: string;
}
```

Change interface:

```ts
  sendMessage: (
    agentId: string,
    orgId: string,
    message: string,
    actorUserId?: string,
    options?: SendMessageOptions
  ) => Promise<void>;
```

Change implementation signature:

```ts
  sendMessage: async (agentId, orgId, message, actorUserId, options) => {
```

Pass options to `streamChat`:

```ts
        executionMode: options?.executionMode ?? "autonomous",
        workflowId: options?.workflowId,
```

- [ ] **Step 2: Extend streamChat payload**

In `streamChat` parameters, add:

```ts
  executionMode: ChatExecutionMode;
  workflowId?: string;
```

In the `JSON.stringify` body, add:

```ts
      execution_mode: executionMode,
      workflow_id: workflowId || null,
```

- [ ] **Step 3: Load workflows in Chat page**

In `apps/web/app/chat/page.tsx`, import workflow store:

```ts
import { useWorkflowStore } from "@/stores/workflow";
```

Inside `ChatPage`, add:

```ts
  const workflows = useWorkflowStore((state) => state.workflows);
  const refreshWorkflows = useWorkflowStore((state) => state.refreshWorkflows);
```

Add effect import:

```ts
import { useEffect, useState } from "react";
```

Add effect:

```ts
  useEffect(() => {
    if (!workspace || !agentId) return;
    void refreshWorkflows(workspace.orgId, workspace.userId, agentId);
  }, [workspace, agentId, refreshWorkflows]);
```

Pass workflows to ChatPanel:

```tsx
              <ChatPanel agentId={agentId} orgId={orgId} actorUserId={actorUserId} workflows={workflows} />
```

- [ ] **Step 4: Add mode controls to ChatPanel props**

In `apps/web/components/chat/ChatPanel.tsx`, import type:

```ts
import type { WorkflowItem } from "@/types/workflow";
import type { ChatExecutionMode } from "@/stores/chat";
```

Update props:

```ts
  workflows,
}: {
  agentId: string;
  orgId: string;
  actorUserId: string;
  workflows: WorkflowItem[];
}) {
```

Add state:

```ts
  const [executionMode, setExecutionMode] = useState<ChatExecutionMode>("autonomous");
  const publishedWorkflows = workflows.filter((workflow) => workflow.published_version_id);
  const [workflowId, setWorkflowId] = useState("");
```

Update handleSend call:

```ts
    await sendMessage(agentId, orgId, msg, actorUserId, {
      executionMode,
      workflowId: executionMode === "workflow" ? workflowId : undefined,
    });
```

- [ ] **Step 5: Render segmented control and selector**

In `ChatPanel`, above the textarea input area, add:

```tsx
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <div className="inline-flex rounded-lg border border-gray-300 bg-white p-1 text-xs dark:border-gray-600 dark:bg-gray-800">
              <button
                className={`rounded-md px-3 py-1.5 ${executionMode === "autonomous" ? "bg-blue-500 text-white" : "text-gray-600 dark:text-gray-300"}`}
                onClick={() => setExecutionMode("autonomous")}
                type="button"
              >
                自主模式
              </button>
              <button
                className={`rounded-md px-3 py-1.5 ${executionMode === "workflow" ? "bg-blue-500 text-white" : "text-gray-600 dark:text-gray-300"}`}
                onClick={() => setExecutionMode("workflow")}
                type="button"
              >
                流程模式
              </button>
            </div>
            {executionMode === "workflow" ? (
              <select
                className="h-8 rounded-lg border border-gray-300 bg-white px-2 text-xs text-gray-800 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
                onChange={(event) => setWorkflowId(event.target.value)}
                value={workflowId}
              >
                <option value="">选择已发布 Workflow</option>
                {publishedWorkflows.map((workflow) => (
                  <option key={workflow.workflow_id} value={workflow.workflow_id}>
                    {workflow.name}
                  </option>
                ))}
              </select>
            ) : null}
          </div>
```

Change send button disabled condition:

```tsx
              disabled={isGenerating || !input.trim() || (executionMode === "workflow" && !workflowId)}
```

- [ ] **Step 6: Run TypeScript build**

Run:

```bash
npm run build
```

from `apps/web`.

Expected: PASS. If it fails due to missing prop, update every `ChatPanel` usage.

- [ ] **Step 7: Commit**

```bash
git add apps/web/stores/chat.ts apps/web/app/chat/page.tsx apps/web/components/chat/ChatPanel.tsx
git commit -m "feat: add chat execution modes"
```

---

### Task 6: Agent-Centered Workflow Page Copy

**Files:**
- Modify: `apps/web/app/workflows/page.tsx`
- Test: `apps/web` TypeScript build

**Interfaces:**
- Consumes: `selectedAgentId` and current Agent from workspace store.
- Produces: Workflows page that blocks creation without selected Agent and labels the canvas as an Agent workflow strategy.

- [ ] **Step 1: Read selected Agent in Workflows page**

In `apps/web/app/workflows/page.tsx`, add:

```ts
  const agents = useWorkspaceStore((state) => state.agents);
  const selectedAgent = agents.find((agent) => agent.agent_id === selectedAgentId);
```

- [ ] **Step 2: Add no-Agent empty state**

After the workspace empty state, add:

```tsx
  if (!selectedAgentId) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-[#667085]">
        请先在 Agents 中选择或创建一个 Agent，再为它设计 Workflow 策略。
      </div>
    );
  }
```

- [ ] **Step 3: Update visible copy**

Change the canvas header title:

```tsx
<div className="text-sm font-semibold text-[#172033]">Agent Workflow Strategy</div>
```

Change the subtitle:

```tsx
{selectedAgent ? selectedAgent.name : "Selected Agent"} · {selectedWorkflow ? selectedWorkflow.name : "Draft"} · {nodes.length} nodes · {edges.length} edges
```

Change the left panel helper text:

```tsx
<div className="mt-1 text-xs text-[#667085]">Build an optional stable process for the selected Agent.</div>
```

- [ ] **Step 4: Run TypeScript build**

Run:

```bash
npm run build
```

from `apps/web`.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/app/workflows/page.tsx
git commit -m "feat: clarify workflows as agent strategy"
```

---

### Task 7: Documentation Positioning Update

**Files:**
- Modify: `README.md`
- Modify: `docs/CURRENT_STATUS.md`
- Modify: `docs/DEVELOPMENT_PLAN.md`
- Modify: `docs/PROJECT_STRUCTURE.md`

**Interfaces:**
- Consumes: approved design in `docs/superpowers/specs/2026-07-07-agent-workflow-positioning-design.md`.
- Produces: consistent public positioning text.

- [ ] **Step 1: Update README opening**

Replace the first paragraph under `# AgentFlow` with:

```markdown
AgentFlow 是一个开源 Agent 构建与运行平台。核心目标是让用户创建、配置、运行和持续优化 Agent；可视化 Workflow 是 Agent 的可选流程策略，用于把开放式 Agent 能力约束到稳定、可复现、可审计的业务链路中。没有 Workflow 的单 Agent 也可以直接处理任务，适合更自主的对话式和探索式场景。
```

- [ ] **Step 2: Add current status positioning note**

In `docs/CURRENT_STATUS.md`, after the title, add:

```markdown
## 产品主线

当前产品主线收敛为 Agent 构建与运行平台。Agent 默认可自主处理任务；Workflow 绑定到 Agent，作为可选执行策略提供稳定输入输出和流程审计。
```

- [ ] **Step 3: Update development plan goal**

In `docs/DEVELOPMENT_PLAN.md`, replace the bullet:

```markdown
- 前端提供类似 Dify 的可视化工作流搭建体验。
```

with:

```markdown
- 前端以 Agent 工作台为主入口，支持创建、配置、对话和观测 Agent；可视化 Workflow 作为 Agent 的可选流程策略。
```

Add this bullet under project goals:

```markdown
- 单 Agent 不依赖 Workflow 即可运行；Workflow 用于需要稳定输入输出、可复现执行和节点级审计的场景。
```

- [ ] **Step 4: Update project structure notes**

In `docs/PROJECT_STRUCTURE.md`, under `packages/workflow`, add:

```markdown
Workflow 属于 Agent 的可选执行策略。所有 Workflow 都绑定 `agent_id`，用于在需要稳定流程时约束 Agent 的执行链路；自主 Agent 对话不依赖 Workflow。
```

- [ ] **Step 5: Commit**

```bash
git add README.md docs/CURRENT_STATUS.md docs/DEVELOPMENT_PLAN.md docs/PROJECT_STRUCTURE.md
git commit -m "docs: clarify agent first positioning"
```

---

### Task 8: Final Verification

**Files:**
- Verify only.

**Interfaces:**
- Consumes all earlier tasks.
- Produces verified local implementation.

- [ ] **Step 1: Run backend focused tests**

Run:

```bash
pytest apps/api/tests/test_agents_api.py apps/api/tests/test_chat_workflow_mode.py tests/integration/test_e2e_workflow.py -q
```

Expected: PASS.

- [ ] **Step 2: Run workflow package tests**

Run:

```bash
pytest packages/workflow/tests tests/integration/test_e2e_workflow.py -q
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run from `apps/web`:

```bash
npm run build
```

Expected: PASS.

- [ ] **Step 4: Inspect git status**

Run:

```bash
git status --short
```

Expected: no uncommitted changes.

- [ ] **Step 5: Final commit only if verification changed files**

If verification required fixes, commit them:

```bash
git add <fixed-files>
git commit -m "fix: stabilize agent workflow mode"
```

If no files changed, do not create an empty commit.

---

## Self-Review

Spec coverage:

- Agent is primary product surface: Tasks 4, 6, 7.
- Workflow optional and bound to Agent: Tasks 1, 3, 6.
- Chat autonomous default: Tasks 2, 5.
- Chat workflow mode with published Workflow: Tasks 2, 5.
- Session messages for both modes: Task 2.
- Docs update: Task 7.
- Tests and verification: Tasks 1, 2, 3, 4, 5, 6, 8.

Placeholder scan:

- No unresolved placeholder wording or unspecified edge handling remains.
- Every task has exact file paths, commands, and expected outcomes.

Type consistency:

- Backend uses `default_workflow_id`.
- Frontend form uses `defaultWorkflowId` and maps to `default_workflow_id`.
- Chat API uses `execution_mode` and `workflow_id`.
- Chat store uses `executionMode` and `workflowId` and serializes to API field names.
