# Gateway Usage Metering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist one trustworthy, tenant-isolated usage event for every real LLM provider attempt and expose organization-scoped API/model/cache usage summaries.

**Architecture:** Keep provider protocol parsing in the Gateway, but inject a single asynchronous `UsageRecorder` at each Gateway terminal path. The recorder persists immutable MySQL facts; metering APIs aggregate those facts rather than the process-local Gateway log. Gateway callers supply server-derived execution context so Chat, Workflow, and direct Gateway traffic receive the same attribution semantics.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, MySQL 8, Pydantic, pytest, existing Next.js API client.

## Global Constraints

- Work only on `feat/agent-default-workflow`; preserve its Agent-first and default-Workflow contracts.
- A Provider-reported usage field is actual usage; missing usage is `NULL`/`unknown`, never zero or a character-count estimate.
- Provider prompt-cache usage and platform Redis/result-cache metrics are separate facts and separate UI labels.
- The event table must not store Prompt, Completion, API keys, Authorization headers, or reversible plain prefix hashes.
- Use JWT-derived authenticated identity and server-side resource context for organization attribution; never trust request-body `org_id` or `actor_user_id` for authorization or accounting.
- First release provides metering and optional estimated cost fields only; it does not debit credits, create invoices, or enforce token budgets.

---

## File Structure

- `apps/api/app/models/metering.py`: immutable usage-event ORM and versioned model-price ORM.
- `apps/api/app/services/db/metering_db.py`: idempotent event persistence and aggregate queries.
- `apps/api/app/services/metering.py`: normalized usage types, HMAC prefix fingerprinting, and asynchronous recorder.
- `apps/api/app/gateway/llm.py`: provider usage normalization, final stream-usage handling, and recorder hooks.
- `apps/api/app/routes/gateway.py`: authenticated direct Gateway execution that supplies trusted attribution.
- `apps/api/app/routes/metering.py`: read-only summary, prefix, and event APIs with member/RBAC enforcement.
- `apps/api/app/schemas/metering.py`: typed filters and redacted response contracts.
- `apps/api/app/services/workflow_execution.py` and `apps/api/app/routes/chat.py`: pass Agent/Session/Workflow/Run context to Gateway calls.
- `apps/api/alembic/versions/20260714_0002_add_llm_usage_events.py`: durable MySQL schema and indexes.
- `apps/web/app/insights/page.tsx` and `apps/web/lib/api.ts`: administrator-facing usage insight screen and typed API client.

## Task 1: Add durable, idempotent metering storage

**Files:**
- Create: `apps/api/app/models/metering.py`
- Modify: `apps/api/app/models/__init__.py`
- Create: `apps/api/app/services/db/metering_db.py`
- Create: `apps/api/alembic/versions/20260714_0002_add_llm_usage_events.py`
- Create: `apps/api/tests/test_metering_db.py`

**Interfaces:**
- Produces `LLMUsageEventModel` with unique `(org_id, gateway_call_id)` and nullable token/cache/cost fields.
- Produces `metering_db.record_event(session, event: UsageEventInput) -> LLMUsageEventModel`.
- Produces `metering_db.aggregate_usage(session, filters: UsageFilters, group_by: str) -> list[UsageAggregate]`.

- [ ] **Step 1: Write failing persistence and aggregation tests**

```python
@pytest.mark.asyncio
async def test_record_event_is_idempotent_and_preserves_unknown_usage(session):
    event = UsageEventInput(
        gateway_call_id="llm_call_1", org_id="org_1", source="gateway_api",
        api_name="chat.completions", provider_key="openai", model="gpt-4o",
        dispatch_status="dispatched", usage_status="unavailable",
        input_tokens=None, output_tokens=None, cache_usage_status="unknown",
    )
    first = await metering_db.record_event(session, event)
    second = await metering_db.record_event(session, event)
    assert first.event_id == second.event_id
    assert first.input_tokens is None
    assert first.cache_read_input_tokens is None

@pytest.mark.asyncio
async def test_aggregate_usage_groups_only_known_token_values(session):
    await metering_db.record_event(session, reported_event("org_1", "gpt-4o", 12, 8, 5))
    await metering_db.record_event(session, unavailable_event("org_1", "gpt-4o"))
    rows = await metering_db.aggregate_usage(session, UsageFilters(org_id="org_1"), "model")
    assert rows[0].input_tokens == 12
    assert rows[0].cache_read_input_tokens == 5
    assert rows[0].unknown_usage_calls == 1
```

- [ ] **Step 2: Run the focused tests to verify the missing contract**

Run: `pytest apps/api/tests/test_metering_db.py -q`

Expected: FAIL because `UsageEventInput`, `metering_db`, and the metering ORM do not exist.

- [ ] **Step 3: Implement the model, migration, and DB service**

```python
class LLMUsageEventModel(Base):
    __tablename__ = "llm_usage_events"
    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    gateway_call_id: Mapped[str] = mapped_column(String(64), nullable=False)
    org_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    api_name: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_key: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    dispatch_status: Mapped[str] = mapped_column(String(32), nullable=False)
    usage_status: Mapped[str] = mapped_column(String(32), nullable=False)
    cache_usage_status: Mapped[str] = mapped_column(String(32), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_read_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    __table_args__ = (UniqueConstraint("org_id", "gateway_call_id"),)
```

Create the Alembic revision with the full event columns from the approved spec, `model_prices`, foreign-key-safe nullable attribution columns, and indexes on `(org_id, created_at)`, `(org_id, provider_key, model, created_at)`, and `(org_id, agent_id, created_at)`. Import both models in `app.models.__init__`; use `insert(...).on_duplicate_key_update` only for terminal fields that are still unset, so a replay cannot replace reported usage.

- [ ] **Step 4: Run persistence, migration, and existing DB tests**

Run: `pytest apps/api/tests/test_metering_db.py apps/api/tests/test_model_provider_store.py -q`

Expected: PASS; a duplicate call ID yields one row, nullable usage remains nullable, and existing provider storage behavior is unchanged.

- [ ] **Step 5: Commit the storage slice**

```bash
git add apps/api/app/models/metering.py apps/api/app/models/__init__.py apps/api/app/services/db/metering_db.py apps/api/alembic/versions/20260714_0002_add_llm_usage_events.py apps/api/tests/test_metering_db.py
git commit -m "feat: persist LLM usage events"
```

## Task 2: Normalize provider usage and record every Gateway terminal state

**Files:**
- Modify: `apps/api/app/gateway/llm.py`
- Create: `apps/api/app/services/metering.py`
- Modify: `apps/api/tests/test_llm_gateway.py`
- Create: `apps/api/tests/test_gateway_usage_recorder.py`

**Interfaces:**
- Consumes `UsageEventInput` from Task 1.
- Produces `NormalizedUsage` with nullable fields and `usage_status`/`cache_usage_status`.
- Produces `UsageRecorder.record_started(context)` and `UsageRecorder.record_terminal(call_id, outcome)`.
- Produces `LLMGateway(..., usage_recorder: UsageRecorder | None)`.

- [ ] **Step 1: Write failing Gateway contract tests**

```python
@pytest.mark.asyncio
async def test_gateway_records_provider_cache_read_without_inventing_cache_miss(recorder):
    gateway = LLMGateway(providers={"mock": UsageProvider({"prompt_tokens": 20, "completion_tokens": 4, "prompt_cache_hit_tokens": 10})}, usage_recorder=recorder)
    await gateway.generate(LLMCallRequest(provider="mock", model="m", prompt="x", metadata={"org_id": "org_1"}))
    event = recorder.events[0]
    assert event.input_tokens == 20
    assert event.cache_read_input_tokens == 10
    assert event.cache_miss_input_tokens == 10

@pytest.mark.asyncio
async def test_gateway_marks_stream_without_final_usage_as_unavailable(recorder):
    gateway = LLMGateway(providers={"mock": StreamProvider(["a", "b"])}, usage_recorder=recorder)
    assert [chunk async for chunk in gateway.stream_generate(request("org_1"))] == ["a", "b"]
    assert recorder.events[0].usage_status == "unavailable"
    assert recorder.events[0].output_tokens is None
```

- [ ] **Step 2: Run the focused contract tests to verify failure**

Run: `pytest apps/api/tests/test_gateway_usage_recorder.py -q`

Expected: FAIL because Gateway has no recorder and stream usage is currently character-count based.

- [ ] **Step 3: Implement explicit usage normalization and final stream usage**

```python
@dataclass(frozen=True, slots=True)
class NormalizedUsage:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    cache_read_input_tokens: int | None
    cache_miss_input_tokens: int | None
    usage_status: str
    cache_usage_status: str

def normalize_usage(raw: dict[str, object]) -> NormalizedUsage:
    input_tokens = _integer_or_none(raw.get("prompt_tokens") or raw.get("input_tokens"))
    output_tokens = _integer_or_none(raw.get("completion_tokens") or raw.get("output_tokens"))
    cache_read = _integer_or_none(raw.get("prompt_cache_hit_tokens") or raw.get("cached_tokens"))
    cache_status = "known" if cache_read is not None else "unknown"
    cache_miss = input_tokens - cache_read if input_tokens is not None and cache_read is not None else None
    total = _integer_or_none(raw.get("total_tokens"))
    return NormalizedUsage(input_tokens, output_tokens, total or _sum_known(input_tokens, output_tokens), cache_read, cache_miss, "provider_final" if input_tokens is not None or output_tokens is not None else "unavailable", cache_status)
```

Make `OpenAICompatibleProvider._build_payload(..., stream=True)` request `stream_options={"include_usage": True}`. Its stream parser must return text events plus an optional final usage payload; `LLMGateway.stream_generate` yields only text while sending the final normalized usage to the recorder. In `generate`, `stream_generate`, provider-not-found, rate-limited, and exception paths create exactly one terminal recorder update. Delete the `completion_chars // 4` accounting path.

- [ ] **Step 4: Run gateway regression tests**

Run: `pytest apps/api/tests/test_llm_gateway.py apps/api/tests/test_gateway_usage_recorder.py -q`

Expected: PASS; provider usage is recorded exactly, missing cache remains unknown, and stream text behavior remains unchanged.

- [ ] **Step 5: Commit the Gateway slice**

```bash
git add apps/api/app/gateway/llm.py apps/api/app/services/metering.py apps/api/tests/test_llm_gateway.py apps/api/tests/test_gateway_usage_recorder.py
git commit -m "feat: record normalized gateway usage"
```

## Task 3: Enforce trusted context and wire Chat and Workflow attribution

**Files:**
- Modify: `apps/api/app/routes/gateway.py`
- Modify: `apps/api/app/schemas/gateway.py`
- Modify: `apps/api/app/routes/chat.py`
- Modify: `apps/api/app/services/workflow_execution.py`
- Modify: `apps/api/tests/test_llm_gateway.py`
- Modify: `apps/api/tests/test_chat_workflow_mode.py`
- Create: `apps/api/tests/test_metering_attribution.py`

**Interfaces:**
- Consumes `AuthenticatedUser`, `membership_db.assert_org_access`, and `UsageRecorder` from Task 2.
- Produces Gateway metadata with `org_id`, `actor_user_id`, `agent_id`, `session_id`, `workflow_id`, `workflow_version_id`, `workflow_run_id`, and `workflow_node_id` only when available.

- [ ] **Step 1: Write authorization and attribution tests**

```python
def test_gateway_generate_rejects_unauthenticated_requests(client):
    response = client.post("/gateway/llm/generate", json={"org_id": "org_1", "actor_user_id": "spoofed", "provider": "mock", "model": "m", "prompt": "hello"})
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_workflow_llm_usage_contains_run_and_node_context(executed_workflow, usage_events):
    event = usage_events.single()
    assert event.agent_id == executed_workflow.agent_id
    assert event.workflow_run_id == executed_workflow.run_id
    assert event.workflow_node_id == "llm_1"
```

- [ ] **Step 2: Run the authorization and attribution tests to verify failure**

Run: `pytest apps/api/tests/test_metering_attribution.py apps/api/tests/test_chat_workflow_mode.py -q`

Expected: FAIL because routes accept body identity and Workflow callbacks omit run/node metadata.

- [ ] **Step 3: Implement authenticated route context and propagation**

Use `auth: AuthenticatedUser` in direct Gateway and Chat handlers; derive organization from the selected Agent/Provider resource and verify membership with `membership_db.assert_org_access`. Remove `actor_user_id` and `org_id` from the externally writable `LLMGenerateRequest`; retain only provider, model, prompt, and parameters. Pass a `UsageContext` to every temporary `LLMGateway` constructed by direct Gateway, Chat, and `WorkflowExecutionService._execute_llm_node`.

```python
context = UsageContext(
    org_id=run.org_id,
    actor_user_id=actor_user_id,
    agent_id=run.agent_id,
    workflow_id=run.workflow_id,
    workflow_version_id=run.version_id,
    workflow_run_id=run.run_id,
    workflow_node_id=str(config["id"]),
    source="workflow_node",
    api_name="chat.completions",
)
```

Bind node IDs in the executor callback rather than inferring them from output data. For autonomous Chat, propagate Agent and Session IDs; for workflow Chat, use the Run created by `WorkflowExecutionService`. Recorder ownership stays per request/session and commits its event through the same SQLAlchemy session before the route commits.

- [ ] **Step 4: Run focused API, Chat, and Workflow tests**

Run: `pytest apps/api/tests/test_metering_attribution.py apps/api/tests/test_chat_workflow_mode.py apps/api/tests/test_workflow_execution_service.py -q`

Expected: PASS; spoofed body identity has no effect, and each pathway creates one correctly attributed event.

- [ ] **Step 5: Commit the attribution slice**

```bash
git add apps/api/app/routes/gateway.py apps/api/app/schemas/gateway.py apps/api/app/routes/chat.py apps/api/app/services/workflow_execution.py apps/api/tests/test_llm_gateway.py apps/api/tests/test_chat_workflow_mode.py apps/api/tests/test_metering_attribution.py
git commit -m "feat: attribute gateway usage to executions"
```

## Task 4: Expose tenant-isolated metering query APIs

**Files:**
- Create: `apps/api/app/schemas/metering.py`
- Create: `apps/api/app/routes/metering.py`
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/app/services/rbac.py`
- Create: `apps/api/tests/test_metering_api.py`

**Interfaces:**
- Consumes `metering_db.aggregate_usage`, `AuthenticatedUser`, and organization membership.
- Produces `GET /metering/usage/summary`, `GET /metering/usage/by-prefix`, and `GET /metering/usage/events`.

- [ ] **Step 1: Write API contract tests**

```python
def test_usage_summary_groups_by_api_and_model_for_org_admin(client, admin_headers, usage_event_factory):
    usage_event_factory(org_id="org_1", api_name="chat.completions", model="gpt-4o", input_tokens=10, output_tokens=2)
    response = client.get("/metering/usage/summary?group_by=model", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["groups"][0]["model"] == "gpt-4o"
    assert response.json()["groups"][0]["total_tokens"] == 12

def test_usage_events_never_leak_cross_org_or_prompt_content(client, admin_headers, usage_event_factory):
    usage_event_factory(org_id="org_2", api_name="chat.completions", model="secret", input_tokens=9)
    response = client.get("/metering/usage/events", headers=admin_headers)
    assert response.status_code == 200
    assert "secret" not in response.text
    assert "prompt_preview" not in response.text
```

- [ ] **Step 2: Run API tests to verify the endpoint is absent**

Run: `pytest apps/api/tests/test_metering_api.py -q`

Expected: FAIL with 404 because the metering router is not registered.

- [ ] **Step 3: Implement schemas, router, and permissions**

Define time-bounded filters with default seven-day range, explicit `hour|day` granularity, and allowed `group_by` values `api|provider|model|agent|workflow|source`. Gate aggregate and event endpoints behind organization membership and `Permission.ORGANIZATION_BILLING`; add that permission to `OrganizationRole.ADMIN` for read-only use. Event responses expose IDs, timestamps, dimensions, token fields, cache status, latency, status, and data-quality flags only.

```python
@router.get("/usage/summary", response_model=UsageSummaryResponse)
async def usage_summary(filters: UsageFilters = Depends(), auth: AuthenticatedUser, session: AsyncSession = Depends(get_db_session)):
    await membership_db.assert_org_access(session, auth.user_id, filters.org_id)
    await require_permission(session, auth, filters.org_id, Permission.ORGANIZATION_BILLING)
    return UsageSummaryResponse.from_rows(await metering_db.aggregate_usage(session, filters.with_org(auth.org_id), filters.group_by))
```

Do not reuse `/gateway/llm/logs`; remove `prompt_preview` from its response contract and make it an authenticated, organization-filtered short-term diagnostic endpoint.

- [ ] **Step 4: Run API and RBAC tests**

Run: `pytest apps/api/tests/test_metering_api.py apps/api/tests/test_rbac.py -q`

Expected: PASS; only authorized organization users can access their own aggregates and no event payload includes sensitive content.

- [ ] **Step 5: Commit the API slice**

```bash
git add apps/api/app/schemas/metering.py apps/api/app/routes/metering.py apps/api/app/main.py apps/api/app/services/rbac.py apps/api/tests/test_metering_api.py
git commit -m "feat: expose metering usage insights"
```

## Task 5: Add organization Insights and run-level usage summaries

**Files:**
- Create: `apps/web/app/insights/page.tsx`
- Create: `apps/web/app/insights/page.test.tsx`
- Modify: `apps/web/lib/api.ts`
- Modify: `apps/web/components/runs/RunSummary.tsx`
- Modify: `apps/web/components/runs/RunsObservability.test.tsx`
- Modify: `apps/web/components/layout/Sidebar.tsx`

**Interfaces:**
- Consumes `GET /metering/usage/summary` and redacted event dimensions from Task 4.
- Produces `/insights` with time, model, API, Agent, Workflow, source, status, cache-status, and data-quality filters.

- [ ] **Step 1: Write failing Insights and Run summary tests**

```tsx
it("labels unknown provider usage as unavailable instead of zero", async () => {
  mockUsageSummary({ groups: [{ model: "gpt-4o", input_tokens: null, unknown_usage_calls: 1 }] });
  render(<InsightsPage />);
  expect(await screen.findByText("Provider 未提供用量")).toBeInTheDocument();
  expect(screen.queryByText("0 Token")).not.toBeInTheDocument();
});

it("keeps provider cache-read tokens separate from platform cache metrics", () => {
  render(<RunSummary run={runWithProviderCacheAndRedisCache} />);
  expect(screen.getByText("Provider 缓存命中 Token")).toBeInTheDocument();
  expect(screen.getByText("平台缓存命中率")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run front-end tests to verify the missing UI**

Run: `npm run test -- --run app/insights/page.test.tsx components/runs/RunsObservability.test.tsx`

Working directory: `apps/web`

Expected: FAIL because `/insights` and the usage API client do not exist.

- [ ] **Step 3: Implement typed client and Insights page**

Add typed `getUsageSummary(filters)` and `getUsageEvents(filters)` client methods. The Insights page defaults to seven days and displays total calls, input/output/total Token, success rate, p50/p95 latency, Provider cache-read Token, cache data coverage, and optional estimated cost only when API returns a priced amount. Show `真实`, `估算`, `未知`, and `不支持` labels exactly as specified; do not render unknown values as zero. Add an “洞察” link in the operating/observability sidebar group and make Agent links carry `agent_id` to preserve the selected Agent filter.

- [ ] **Step 4: Run front-end unit tests and production build**

Run: `npm run test -- --run app/insights/page.test.tsx components/runs/RunsObservability.test.tsx && npm run build`

Working directory: `apps/web`

Expected: PASS; Insights renders correct quality labels and the production build completes.

- [ ] **Step 5: Commit the UI slice**

```bash
git add apps/web/app/insights/page.tsx apps/web/app/insights/page.test.tsx apps/web/lib/api.ts apps/web/components/runs/RunSummary.tsx apps/web/components/runs/RunsObservability.test.tsx apps/web/components/layout/Sidebar.tsx
git commit -m "feat: add usage insights dashboard"
```

## Task 6: Verify migration, API, and user-visible behavior end to end

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/MODULE_11_GATEWAY_LLM.md`
- Modify: `docs/CURRENT_STATUS.md`
- Create: `tests/integration/test_metering_usage_flow.py`

**Interfaces:**
- Consumes all prior tasks.
- Produces a repeatable CI gate for migration, Python meter contracts, web tests, and web build.

- [ ] **Step 1: Write the failing integration scenario**

```python
def test_authenticated_gateway_call_appears_once_in_org_usage_summary(client, admin_headers, configured_provider):
    response = client.post("/gateway/llm/generate", headers=admin_headers, json={"provider": configured_provider.key, "model": "mock-model", "prompt": "summarize"})
    assert response.status_code == 200
    summary = client.get("/metering/usage/summary?group_by=api", headers=admin_headers)
    assert summary.status_code == 200
    assert summary.json()["groups"][0]["calls"] == 1
```

- [ ] **Step 2: Run the integration scenario before final wiring**

Run: `pytest tests/integration/test_metering_usage_flow.py -q`

Expected: FAIL before all previous slices are integrated; PASS after Tasks 1–5.

- [ ] **Step 3: Add CI and documentation**

Run backend tests in CI with `pytest apps/api/tests tests/integration/test_metering_usage_flow.py`; run web tests with `npm ci` then `npm run test -- --run`; retain `npm run build`. Document field semantics, data-quality labels, stream limitations, cache coverage denominator, and the statement that `estimated_cost` is not a supplier invoice.

- [ ] **Step 4: Run the complete verification set**

Run: `pytest apps/api/tests tests/integration/test_metering_usage_flow.py -q`

Run: `npm ci && npm run test -- --run && npm run build`

Working directory for the second command: `apps/web`

Expected: PASS; migration, tenant isolation, usage semantics, API contracts, Insights tests, and production build are green.

- [ ] **Step 5: Commit the verification slice**

```bash
git add .github/workflows/ci.yml docs/MODULE_11_GATEWAY_LLM.md docs/CURRENT_STATUS.md tests/integration/test_metering_usage_flow.py
git commit -m "test: verify gateway usage metering"
```

## Plan Self-Review

- Spec coverage: Tasks 1–2 implement immutable facts and accurate Provider usage; Task 3 establishes trustworthy attribution; Task 4 delivers restricted aggregate/event APIs; Task 5 implements the required insights experience; Task 6 makes the behavior repeatable and documented.
- Scope control: model price rows are reserved for optional estimated-cost display. Credits, invoices, refunds, and budget enforcement have no task because they are outside this spec.
- Type consistency: every Gateway path uses `UsageRecorder` and `UsageContext`; every persistent record uses `UsageEventInput`; every query consumes `UsageFilters` and returns `UsageAggregate`.
