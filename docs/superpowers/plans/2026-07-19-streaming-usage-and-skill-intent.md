# 实时用量进度与 Skill 创建意图 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 在自主对话、显式 Skill 创建和 Workflow 聊天模式中持续展示本地 Token 估算，并以 Provider 终态 usage 校准，同时阻止非明确请求创建 Skill。

**Architecture:** 后端以一个小型、可序列化的用量报告器统一生成 context_preflight、context_progress 和 context_usage 事件。聊天路由直接消费报告器；Workflow 仅在聊天调用时经异步队列转发节点进度，保留执行器与后台 Worker 的原有同步结果契约。前端按调用键汇总估算与终态值并清楚标注校准状态。

**Tech Stack:** Python 3.11、FastAPI SSE、SQLAlchemy async、LangGraph、Next.js 15、React 19、TypeScript、Zustand、Vitest、pytest。

## Global Constraints

- 本地估算不得写成 Provider 的实际计费 usage，也不得把 unavailable 转为零。
- 现有 context_preflight、context_progress、context_usage 和 skill_created 的事件名称必须保持兼容。
- Provider 终态 usage 可覆盖估算；Provider 未报告 usage 时保留估算并显示 unavailable。
- 非明确 Skill 创建请求必须继续走普通聊天和既有 Skill 检索路径，且不得写文件、写数据库或变更授权。
- 普通 API 与 Worker 的 Workflow 执行不得因聊天 SSE 回调而改变结果或持久化语义。
- 每个任务先写失败测试，确认失败后再写最小实现；每项任务单独提交。

## 文件结构

- Modify: apps/api/app/services/skill_creator.py — 严格、默认拒绝的 Skill 创建意图解析。
- Modify: apps/api/tests/test_chat_streaming_skill_creator.py — 意图正反例与聊天创建副作用回归。
- Create: apps/api/app/services/stream_usage.py — 组装和序列化每次调用的预检、估算和终态用量事件。
- Create: apps/api/tests/test_stream_usage.py — 报告器的纯函数和状态转换测试。
- Modify: apps/api/app/gateway/llm.py — 复用 Workflow 请求构建逻辑，并为 Workflow LLM 节点提供流式文本回调。
- Modify: apps/api/tests/test_llm_gateway.py — Workflow 节点流式输出与终态 usage 测试。
- Modify: apps/api/app/routes/chat.py — 让自主对话和显式 Skill 创建使用统一报告器；将聊天 Workflow 进度队列转为 SSE。
- Modify: apps/api/app/routes/workflow_runs.py — 暴露仅供聊天使用的 Workflow 异步进度迭代器。
- Modify: apps/api/app/services/workflow_execution.py — 仅聊天调用注入 LLM 节点进度回调。
- Modify: apps/api/tests/test_chat_workflow_mode.py — Workflow 聊天的 SSE 顺序、累计进度和持久化回归。
- Modify: apps/web/stores/chat.ts — 按 usage_key 累积多个调用的估算和终态值。
- Modify: apps/web/components/chat/ChatComposer.tsx — 展示实时估算、部分校准、已校准、不可用和活动 Workflow 节点。
- Modify: apps/web/components/chat/ChatStore.test.ts — 前端 SSE 聚合状态测试。
- Modify: apps/web/components/chat/ChatComposer.test.tsx — 文案与状态可视化测试。

---

### Task 1: 收紧 Skill 创建意图并锁定无副作用回归

**Files:**
- Modify: apps/api/app/services/skill_creator.py:18-48
- Modify: apps/api/tests/test_chat_streaming_skill_creator.py:1-30
- Modify: apps/api/tests/test_chat_streaming_skill_creator.py: add route-level side-effect test

**Interfaces:**
- Consumes: 用户原始聊天消息。
- Produces: SkillIntent，其中 is_skill_request 只在明确命令式创建 Skill 时为 true，topic 为移除命令词后的主题。
- Preserves: chat.py 现有的普通 Skill discovery 分支和 skill_created 事件名。

- [ ] **Step 1: 写解析器失败测试**

在 test_chat_streaming_skill_creator.py 的 imports 中加入 import pytest，并增加以下参数化测试。它们在旧的宽泛子串实现下必须失败：

~~~
@pytest.mark.parametrize(
    "message",
    [
        "帮我创建一个工作流，完成客户投诉分流",
        "生成一个销售周报模板",
        "新建一个 API 接口",
        "请解释如何创建一个 Skill",
        "是否能生成技能说明？",
    ],
)
def test_rejects_non_imperative_or_non_skill_creation(message: str) -> None:
    assert detect_skill_creation_request(message).is_skill_request is False


@pytest.mark.parametrize(
    "message, topic",
    [
        ("帮我创建一个用于总结会议纪要的 Skill", "总结会议纪要"),
        ("生成技能：客户投诉分流", "客户投诉分流"),
        ("create a skill for release-note summaries", "release-note summaries"),
    ],
)
def test_accepts_explicit_skill_creation(message: str, topic: str) -> None:
    result = detect_skill_creation_request(message)
    assert result.is_skill_request is True
    assert topic in result.topic
~~~

- [ ] **Step 2: 运行测试并确认当前实现失败**

Run: python -m pytest apps/api/tests/test_chat_streaming_skill_creator.py -q
Expected: 至少五个负例失败，因为裸“创建/生成/新建一个”当前会返回 true。

- [ ] **Step 3: 实现默认拒绝的解析器**

在 skill_creator.py 使用显式正则替换触发词元组。保持 SkillIntent 结构不变：

~~~
_SKILL_OBJECT = r"(?:skill|技能)"
_CONSULTATION_PREFIX = re.compile(r"^(?:请)?\s*(?:解释|介绍|说明|如何|怎么|能否|是否)", re.IGNORECASE)
_CHINESE_CREATE = re.compile(
    rf"^(?:请|帮我|请帮我)?\s*(?:创建|生成|新建)\s*(?:一个)?\s*{_SKILL_OBJECT}\s*(?:[:：]|用于|用来|关于)?\s*(?P<topic>.+)$",
    re.IGNORECASE,
)
_CHINESE_SUFFIX_CREATE = re.compile(
    rf"^(?:请|帮我|请帮我)?\s*(?:创建|生成|新建)\s*(?:一个)?\s*(?:用于|用来|关于)?\s*(?P<topic>.+?)\s*(?:的)?\s*{_SKILL_OBJECT}$",
    re.IGNORECASE,
)
_ENGLISH_CREATE = re.compile(
    r"^(?:please\s+)?(?:create|generate|new)\s+(?:a\s+)?skill\s+(?:for|about)?\s*(?P<topic>.+)$",
    re.IGNORECASE,
)


def detect_skill_creation_request(message: str) -> SkillIntent:
    normalized = message.strip()
    if not normalized or _CONSULTATION_PREFIX.search(normalized):
        return SkillIntent(is_skill_request=False)
    match = (
        _CHINESE_CREATE.match(normalized)
        or _CHINESE_SUFFIX_CREATE.match(normalized)
        or _ENGLISH_CREATE.match(normalized)
    )
    if match is None:
        return SkillIntent(is_skill_request=False)
    topic = match.group("topic").strip(" ：:-")
    return SkillIntent(is_skill_request=bool(topic), topic=topic)
~~~

不要重新允许没有 Skill 或 技能对象词的裸创建动作。上述 _CHINESE_SUFFIX_CREATE 是唯一允许“先描述用途、后写 Skill”的中文变体。

- [ ] **Step 4: 增加聊天路径无副作用测试**

在同一测试模块中，使用现有 TestClient 或 route dependency mock，发送“创建一个工作流”。替换 write_skill_file、skill_db.create_skill 和 agent_skill_policy_db.set_policy 为会抛出 AssertionError 的 mock。断言流中不含 skill_created 且存在 agent_call。该测试保障路由没有绕过解析器直接写入。

- [ ] **Step 5: 运行任务测试并确认通过**

Run: python -m pytest apps/api/tests/test_chat_streaming_skill_creator.py -q
Expected: PASS，且所有负例都不触发创建。

- [ ] **Step 6: 提交 Task 1**

~~~
git add apps/api/app/services/skill_creator.py apps/api/tests/test_chat_streaming_skill_creator.py
git commit -m "fix: require explicit skill creation intent"
~~~

### Task 2: 建立可复用的流式用量报告器

**Files:**
- Create: apps/api/app/services/stream_usage.py
- Create: apps/api/tests/test_stream_usage.py

**Interfaces:**
- Consumes: provider、model、预检 ContextTokenPreflight、usage_scope、usage_key、可选 workflow_node_id，以及文本 chunk 或 NormalizedUsage。
- Produces: JSON 可序列化字典，包含兼容字段和新增 usage_scope、usage_key、usage_phase、workflow_node_id。
- Used by: chat.py 的自主与 Skill 创建路径，以及 workflow_execution.py 的 LLM 节点回调。

- [ ] **Step 1: 写报告器失败测试**

在 test_stream_usage.py 创建固定 preflight，并断言事件序列与字段：

~~~
def test_reporter_emits_preflight_progress_and_provider_final() -> None:
    reporter = StreamUsageReporter(
        provider="custom",
        model="unknown",
        preflight=ContextTokenPreflight(100, None, "characters_divided_by_4", None, []),
        usage_scope="workflow",
        usage_key="run-1:llm-1",
        workflow_node_id="llm-1",
        token_limit=2400,
    )

    assert reporter.preflight_event()["usage_phase"] == "preflight"
    progress = reporter.append_text("x" * 40)
    assert progress["usage_phase"] == "estimated"
    assert progress["output_tokens"] == 10
    final = reporter.final_event(normalize_usage({"prompt_tokens": 120, "completion_tokens": 12}))
    assert final["usage_phase"] == "provider_final"
    assert final["input_tokens"] == 120
    assert final["workflow_node_id"] == "llm-1"
~~~

- [ ] **Step 2: 运行失败测试**

Run: python -m pytest apps/api/tests/test_stream_usage.py -q
Expected: FAIL，因为模块和 StreamUsageReporter 尚不存在。

- [ ] **Step 3: 实现 StreamUsageReporter**

创建 stream_usage.py。报告器只负责事件数据，不负责 SSE 格式化、持久化或网络调用：

~~~
@dataclass(slots=True)
class StreamUsageReporter:
    provider: str
    model: str
    preflight: ContextTokenPreflight
    usage_scope: Literal["chat", "skill_create", "workflow"]
    usage_key: str
    token_limit: int
    workflow_node_id: str | None = None
    _text: list[str] = field(default_factory=list)

    def preflight_event(self) -> dict[str, object]:
        return self._base(
            usage_phase="preflight",
            input_tokens=self.preflight.input_tokens,
            output_tokens=0,
            context_tokens=self.preflight.input_tokens,
            token_limit=self.token_limit,
            tokenizer_status=self.preflight.status,
            tokenizer=self.preflight.tokenizer,
            stable_prefix_tokens=self.preflight.stable_prefix_tokens,
            prompt_breakdown=self.preflight.breakdown,
        )

    def append_text(self, text: str) -> dict[str, object]:
        self._text.append(text)
        output_tokens = count_stream_output_tokens(
            provider=self.provider, model=self.model, text="".join(self._text)
        )
        return self._base(
            usage_phase="estimated",
            input_tokens=self.preflight.input_tokens,
            output_tokens=output_tokens,
            context_tokens=(
                self.preflight.input_tokens + output_tokens
                if self.preflight.input_tokens is not None
                else None
            ),
            token_limit=self.token_limit,
            output_token_status=(
                "official_tokenizer"
                if self.preflight.status == "official_tokenizer"
                else "characters_divided_by_4"
            ),
        )
~~~

实现 final_event 与 unavailable_final_event。两者均包含 token_limit；final_event 使用 NormalizedUsage，不得用本地估算代替缺失 Provider 字段。

- [ ] **Step 4: 运行报告器测试**

Run: python -m pytest apps/api/tests/test_stream_usage.py -q
Expected: PASS。

- [ ] **Step 5: 提交 Task 2**

~~~
git add apps/api/app/services/stream_usage.py apps/api/tests/test_stream_usage.py
git commit -m "feat: add reusable streaming usage reporter"
~~~

### Task 3: 为 Workflow LLM 节点暴露流式文本回调

**Files:**
- Modify: apps/api/app/gateway/llm.py:398-443
- Modify: apps/api/tests/test_llm_gateway.py

**Interfaces:**
- Consumes: Workflow 节点 config、node_input 和异步 on_text 回调。
- Produces: 与现有 generate_from_workflow_node 相同的节点输出字典；回调按 Provider 文本 chunk 调用。
- Preserves: generate_from_workflow_node、后台 Worker 和非聊天 Workflow 调用的现有行为。

- [ ] **Step 1: 写 Gateway 失败测试**

增加 fake provider，其 stream_generate 依次返回 LLMStreamChunk(text="A")、LLMStreamChunk(text="B") 和终态 usage。测试新方法：

~~~
async def test_stream_workflow_node_reports_chunks_and_returns_existing_shape() -> None:
    seen: list[str] = []
    result = await gateway.stream_generate_from_workflow_node(
        config=workflow_config,
        node_input={"workflow_input": {"text": "hi"}, "upstream": {}},
        on_text=seen.append,
    )
    assert seen == ["A", "B"]
    assert result["text"] == "AB"
    assert result["usage"]["prompt_tokens"] == 10
~~~

若 on_text 必须异步，测试使用 async def on_text(text): seen.append(text)。同时断言 gateway.last_normalized_usage 只在流耗尽后有 Provider 值。

- [ ] **Step 2: 运行失败测试**

Run: python -m pytest apps/api/tests/test_llm_gateway.py -q
Expected: FAIL，因为 stream_generate_from_workflow_node 尚不存在。

- [ ] **Step 3: 提取 Workflow 请求构建并实现流式方法**

将当前 generate_from_workflow_node 的请求构建提取为私有方法，确保 metadata、prefix_hash、prompt 和 parameters 完全相同：

~~~
def build_workflow_request(
    self, config: dict[str, Any], node_input: dict[str, Any]
) -> tuple[LLMCallRequest, dict[str, object]]:
    provider = str(config.get("provider") or "")
    model = str(config.get("model") or "")
    if not provider or not model:
        raise GatewayProviderError("LLM 节点缺少真实模型供应商或模型配置")
    compiled = self._compile_workflow_prompt(config=config, node_input=node_input)
    request = LLMCallRequest(
        provider=provider,
        model=model,
        prompt=str(compiled["compiled_prompt"]),
        parameters={
            "temperature": config.get("temperature", 0),
            "max_tokens": config.get("max_tokens"),
        },
        metadata={
            "source": "workflow_node",
            "org_id": config.get("_org_id", ""),
            "actor_user_id": config.get("_actor_user_id", ""),
            "agent_id": config.get("_agent_id", ""),
            "workflow_id": config.get("_workflow_id", ""),
            "workflow_version_id": config.get("_workflow_version_id", ""),
            "workflow_run_id": config.get("_workflow_run_id", ""),
            "workflow_node_id": config.get("_workflow_node_id", ""),
            "api_name": "chat.completions",
            "upstream_node_count": len(node_input.get("upstream", {})),
        },
        prefix_hash=str(compiled["prefix_hash"]),
    )
    return request, compiled


async def stream_generate_from_workflow_node(
    self,
    config: dict[str, Any],
    node_input: dict[str, Any],
    on_text: Callable[[str], Awaitable[None]],
) -> dict[str, Any]:
    request, compiled = self.build_workflow_request(config, node_input)
    parts: list[str] = []
    stream = self.stream_generate(request)
    try:
        async for text in stream:
            parts.append(text)
            await on_text(text)
    finally:
        await stream.aclose()
    return {
        "text": "".join(parts),
        "provider": request.provider,
        "model": request.model,
        "usage": dict(self.last_raw_usage),
        "upstream": node_input.get("upstream", {}),
        "prefix_hash": str(compiled["prefix_hash"]),
    }
~~~

在 LLMGateway 初始化时添加 last_raw_usage: dict[str, object] = {}；在 generate 和 stream_generate 的成功终态分别以原始 Provider usage 更新它，在 unavailable 终态设为空字典。让原 generate_from_workflow_node 改为复用 build_workflow_request 后继续调用 generate。导入 collections.abc 的 Awaitable 与 Callable。

- [ ] **Step 4: 运行 Gateway 测试**

Run: python -m pytest apps/api/tests/test_llm_gateway.py -q
Expected: PASS。

- [ ] **Step 5: 提交 Task 3**

~~~
git add apps/api/app/gateway/llm.py apps/api/tests/test_llm_gateway.py
git commit -m "feat: stream workflow llm node output"
~~~

### Task 4: 让自主对话和显式 Skill 创建使用统一用量事件

**Files:**
- Modify: apps/api/app/routes/chat.py:512-808
- Modify: apps/api/tests/test_chat_streaming_skill_creator.py
- Modify: apps/api/tests/test_context_tokens.py

**Interfaces:**
- Consumes: StreamUsageReporter 和 LLMGateway.stream_generate。
- Produces: 每次模型调用严格按照 context_preflight、零到多个 context_progress、context_usage 的事件顺序。
- Depends on: Task 1、Task 2。

- [ ] **Step 1: 写路由失败测试**

对独立的聊天流生成器注入 fake gateway，断言普通自主对话和明确创建 Skill 均符合：

~~~
assert event_names == [
    "context_preflight",
    "context_progress",
    "context_progress",
    "context_usage",
]
assert progress_payloads[1]["output_tokens"] > progress_payloads[0]["output_tokens"]
assert final_payload["usage_phase"] == "provider_final"
~~~

Skill 测试还应断言：在第二个 progress 后、skill_created 前不产生 token 事件；skill_created 只在 Markdown 校验、write_skill_file、create_skill 和 set_policy 都成功后出现。

- [ ] **Step 2: 运行测试并确认失败**

Run: python -m pytest apps/api/tests/test_chat_streaming_skill_creator.py apps/api/tests/test_context_tokens.py -q
Expected: FAIL，因为 Skill 创建仍调用 LLMCallerAdapter.call，且现有事件不包含 usage_key 与 usage_phase。

- [ ] **Step 3: 写共享的聊天流辅助逻辑**

在 chat.py 新增以下事件值对象与 async generator。它返回更新对象，而不是尝试从 async generator 返回最终文本：

~~~
@dataclass(frozen=True, slots=True)
class StreamCallUpdate:
    kind: Literal["preflight", "chunk", "final"]
    payload: dict[str, object]
    text: str = ""


async def _iterate_call_with_usage(
    gateway: LLMGateway,
    request: LLMCallRequest,
    reporter: StreamUsageReporter,
 ) -> AsyncIterator[StreamCallUpdate]:
    yield StreamCallUpdate("preflight", reporter.preflight_event())
    stream = gateway.stream_generate(request)
    try:
        async for chunk in stream:
            yield StreamCallUpdate("chunk", reporter.append_text(chunk), text=chunk)
    finally:
        await stream.aclose()
    usage = gateway.last_normalized_usage
    payload = reporter.final_event(usage) if usage is not None else reporter.unavailable_final_event()
    yield StreamCallUpdate("final", payload)
~~~

自主对话消费该迭代器时，对每个 chunk 将 update.text 追加到 response_parts、发送 token 事件和 context_progress；preflight 与 final 分别发送 context_preflight 与 context_usage。显式 Skill 创建也追加 update.text 到 raw_skill_parts 并发送 context_progress，但不发送 token。两条路径都必须保持 preflight、零到多个 progress、final 的顺序。

替换自主对话中手写的 preflight/progress/final块。自主与显式 Skill 创建的 StreamUsageReporter 都传入 token_limit=_memory_compaction_threshold(agent.context_token_limit)。Skill 创建分支构造真实 Skill Creator prompt 的 LLMCallRequest、单独计算 preflight，并使用不发送 token 的相同辅助逻辑。

- [ ] **Step 4: 补充失败和取消语义**

为 gateway.last_normalized_usage 为 unavailable、流取消和 Markdown 校验失败增加测试。每种情况下最后可见事件必须表明 unavailable 或 error；绝不能发送 provider_final 或 skill_created。

- [ ] **Step 5: 运行任务测试**

Run: python -m pytest apps/api/tests/test_chat_streaming_skill_creator.py apps/api/tests/test_context_tokens.py apps/api/tests/test_llm_gateway.py -q
Expected: PASS。

- [ ] **Step 6: 提交 Task 4**

~~~
git add apps/api/app/routes/chat.py apps/api/tests/test_chat_streaming_skill_creator.py apps/api/tests/test_context_tokens.py
git commit -m "feat: stream usage through chat and skill creation"
~~~

### Task 5: 经聊天专用队列转发 Workflow LLM 进度

**Files:**
- Modify: apps/api/app/services/workflow_execution.py:34-151
- Modify: apps/api/app/routes/workflow_runs.py:91-106
- Modify: apps/api/app/routes/chat.py:370-432
- Modify: apps/api/tests/test_chat_workflow_mode.py

**Interfaces:**
- Consumes: 可选 async on_usage_event 回调，其参数为 StreamUsageReporter 产生的事件字典。
- Produces: 一个只用于聊天的异步事件迭代器；进度事件在 run_finished 前发送，最终仍返回 WorkflowRunModel。
- Depends on: Task 2、Task 3。

- [ ] **Step 1: 写 Workflow SSE 失败测试**

在 test_chat_workflow_mode.py 增加一个含 start、llm、end 的发布流程，并注入分两块返回文本的 fake Provider。解析 SSE 并断言：

~~~
workflow_progress = [event for event in events if event["event"] == "context_progress"]
assert len(workflow_progress) >= 2
assert all(item["usage_scope"] == "workflow" for item in workflow_progress)
assert all(item["workflow_node_id"] == "llm" for item in workflow_progress)
assert events.index(workflow_progress[-1]) < index_of_run_finished
assert persisted_run["status"] == "succeeded"
~~~

增加一个 Provider 未返回 usage 的场景，断言最后 context_usage 的 usage_phase 是 unavailable，而不是 provider_final。

- [ ] **Step 2: 运行失败测试**

Run: python -m pytest apps/api/tests/test_chat_workflow_mode.py -q
Expected: FAIL，因为 Workflow 聊天当前只在同步执行结束后发 token。

- [ ] **Step 3: 为执行服务添加可选进度回调**

在 workflow_execution.py 引入 from collections.abc import Awaitable, Callable，并定义 UsageEventCallback = Callable[[dict[str, object]], Awaitable[None]]。为 create_and_execute、execute_existing_run 和 _execute_llm_node 增加可选 on_usage_event 参数，并按下列代码完整转发该参数：

~~~
async def create_and_execute(
    self,
    session: AsyncSession,
    *,
    version_id: str,
    input_data: dict[str, Any],
    actor_user_id: str,
    on_usage_event: UsageEventCallback | None = None,
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
        on_usage_event=on_usage_event,
    )

async def execute_existing_run(
    self,
    session: AsyncSession,
    *,
    run: WorkflowRunModel,
    definition: dict[str, Any],
    input_data: dict[str, Any],
    actor_user_id: str,
    on_usage_event: UsageEventCallback | None = None,
) -> WorkflowRunModel:
    await workflow_run_db.update_run_status(session, run.run_id, "running")
    executor = WorkflowExecutor(
        llm_gateway=lambda config, node_input: self._execute_llm_node(
            session=session,
            config=config,
            node_input=node_input,
            actor_user_id=actor_user_id,
            org_id=run.org_id,
            run=run,
            on_usage_event=on_usage_event,
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
    run: WorkflowRunModel,
    on_usage_event: UsageEventCallback | None = None,
) -> dict[str, Any]:
    if on_usage_event is None:
        return await gateway.generate_from_workflow_node(enriched_config, node_input)
    request, _compiled = gateway.build_workflow_request(enriched_config, node_input)
    reporter = StreamUsageReporter(
        provider=request.provider,
        model=request.model,
        preflight=preflight_chat_context(
            provider=request.provider,
            model=request.model,
            compiled_prompt=request.prompt,
            components=[],
        ),
        usage_scope="workflow",
        usage_key=f"{run.run_id}:{config['id']}",
        workflow_node_id=str(config["id"]),
        token_limit=2400,
    )
    await on_usage_event(reporter.preflight_event())
    result = await gateway.stream_generate_from_workflow_node(
        enriched_config,
        node_input,
        on_text=lambda text: on_usage_event(reporter.append_text(text)),
    )
    usage = gateway.last_normalized_usage
    await on_usage_event(
        reporter.final_event(usage) if usage is not None else reporter.unavailable_final_event()
    )
    return result
~~~

create_and_execute 的版本加载和 run 创建逻辑保持原样，但调用 execute_existing_run 时原样转发 on_usage_event。execute_existing_run 注入到 WorkflowExecutor 的 llm_gateway lambda 必须捕获并传入 on_usage_event。不要改动 RAG、Tool 回调，且无 callback 的所有调用必须保留原 generate 路径。

- [ ] **Step 4: 实现聊天专用队列迭代器**

在 workflow_runs.py 导入 asyncio、contextlib.suppress、dataclasses 的 dataclass/field 与 Literal/AsyncIterator。定义以下聊天专用更新类型，并实现 async generator stream_workflow_version_for_chat。它创建 asyncio.Queue、以 create_task 运行 create_and_execute，并在等待任务结束的同时持续 yield callback 放入的事件。取消生成器时取消 task，并 await task 以关闭 Provider 流：

~~~
@dataclass(frozen=True, slots=True)
class WorkflowChatStreamUpdate:
    kind: Literal["usage", "completed"]
    event_name: str = ""
    payload: dict[str, object] = field(default_factory=dict)
    run: WorkflowRunModel | None = None


async def stream_workflow_version_for_chat(
    session: AsyncSession,
    *,
    version_id: str,
    input_data: dict[str, Any],
    actor_user_id: str,
    token_limit: int,
) -> AsyncIterator[WorkflowChatStreamUpdate]:
    queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()

    async def on_usage_event(payload: dict[str, object]) -> None:
        payload["token_limit"] = token_limit
        await queue.put(payload)

    task = asyncio.create_task(
        workflow_execution_service.create_and_execute(
            session,
            version_id=version_id,
            input_data=input_data,
            actor_user_id=actor_user_id,
            on_usage_event=on_usage_event,
        )
    )
    try:
        while not task.done() or not queue.empty():
            next_payload = asyncio.create_task(queue.get())
            done, _pending = await asyncio.wait(
                {task, next_payload},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if next_payload not in done:
                next_payload.cancel()
                with suppress(asyncio.CancelledError):
                    await next_payload
                continue
            payload = next_payload.result()
            phase = str(payload["usage_phase"])
            event_name = (
                "context_preflight" if phase == "preflight"
                else "context_progress" if phase == "estimated"
                else "context_usage"
            )
            yield WorkflowChatStreamUpdate("usage", event_name, payload)
        yield WorkflowChatStreamUpdate("completed", run=await task)
    finally:
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError):
            await task
~~~

chat.py 的 Workflow 分支改为消费此迭代器：

~~~
async for update in stream_workflow_version_for_chat(
    db,
    version_id=workflow.published_version_id,
    input_data={"text": request.message},
    actor_user_id=actor_user_id,
    token_limit=_memory_compaction_threshold(agent.context_token_limit),
):
    if update.kind == "usage":
        yield await emit(update.event_name, **update.payload)
    else:
        run = update.run
~~~

仅在收到最终 run 后序列化 response_text、保存会话消息和发送 run_finished。不要再使用执行完成后再切块伪装流式的做法。

- [ ] **Step 5: 运行 Workflow 测试**

Run: python -m pytest apps/api/tests/test_chat_workflow_mode.py apps/api/tests/test_workflow_execution_service.py -q
Expected: PASS，既有 Workflow metadata 与 NodeRun 断言保持通过。

- [ ] **Step 6: 提交 Task 5**

~~~
git add apps/api/app/services/workflow_execution.py apps/api/app/routes/workflow_runs.py apps/api/app/routes/chat.py apps/api/tests/test_chat_workflow_mode.py
git commit -m "feat: stream workflow usage into chat"
~~~

### Task 6: 在前端聚合调用级用量并明确校准状态

**Files:**
- Modify: apps/web/stores/chat.ts:42-56, 177-227
- Modify: apps/web/components/chat/ChatComposer.tsx:3-109
- Modify: apps/web/components/chat/ChatStore.test.ts
- Modify: apps/web/components/chat/ChatComposer.test.tsx

**Interfaces:**
- Consumes: context_preflight、context_progress、context_usage 的 usage_key、usage_scope、usage_phase、workflow_node_id。
- Produces: 累计 ContextUsage，calibrationStatus 为 estimated、partially_calibrated、provider_final 或 unavailable，且可选 activeWorkflowNodeId。
- Depends on: Task 4、Task 5。

- [ ] **Step 1: 写前端失败测试**

在 ChatStore.test.ts 模拟同一 SSE chunk 内含两个 Workflow 调用：

~~~
event: context_preflight
data: {"usage_key":"run:llm-a","usage_scope":"workflow","workflow_node_id":"llm-a","input_tokens":100,"usage_phase":"preflight"}

event: context_progress
data: {"usage_key":"run:llm-a","usage_scope":"workflow","workflow_node_id":"llm-a","output_tokens":20,"context_tokens":120,"usage_phase":"estimated"}

event: context_usage
data: {"usage_key":"run:llm-a","usage_scope":"workflow","workflow_node_id":"llm-a","input_tokens":110,"output_tokens":22,"usage_phase":"provider_final","usage_status":"provider_final"}
~~~

断言 store 立即得到 120 的估算、终态更新为 132，并在第二个仍为估算的调用存在时 calibrationStatus 是 partially_calibrated。

在 ChatComposer.test.tsx 使用 contextUsage 的四种状态断言中文文案：

~~~
实时估算
部分已校准
Provider 已校准
Provider 未提供用量
~~~

Workflow 状态还应包含“当前节点：llm-a”。

- [ ] **Step 2: 运行前端测试并确认失败**

Run: npm test -- --run components/chat/ChatStore.test.ts components/chat/ChatComposer.test.tsx
Workdir: apps/web
Expected: FAIL，因为当前 store 只有单次 actualContextUsage，且组件未显示校准状态。

- [ ] **Step 3: 实现按调用键的聚合状态**

在 chat.ts 新增内部 UsageCallState 和聚合函数；不要把每个 progress 事件加入 trace：

~~~
type CalibrationStatus =
  | "estimated"
  | "partially_calibrated"
  | "provider_final"
  | "unavailable";

type UsageCallState = {
  key: string;
  scope: "chat" | "skill_create" | "workflow";
  workflowNodeId: string | null;
  estimatedInputTokens: number | null;
  estimatedOutputTokens: number;
  finalInputTokens: number | null;
  finalOutputTokens: number | null;
  tokenLimit: number;
  phase: "preflight" | "estimated" | "provider_final" | "unavailable";
};

function aggregateUsage(calls: Record<string, UsageCallState>): ActualContextUsage {
  const entries = Object.values(calls);
  const isFinal = (entry: UsageCallState) => entry.phase === "provider_final";
  const inputTokens = entries.reduce<number | null>((total, entry) => {
    const value = isFinal(entry) ? entry.finalInputTokens : entry.estimatedInputTokens;
    return value === null || total === null ? null : total + value;
  }, 0);
  const outputTokens = entries.reduce(
    (total, entry) => total + (isFinal(entry)
      ? entry.finalOutputTokens ?? entry.estimatedOutputTokens
      : entry.estimatedOutputTokens),
    0,
  );
  const finalCount = entries.filter(isFinal).length;
  const calibrationStatus: CalibrationStatus =
    finalCount === entries.length && entries.length > 0 ? "provider_final" :
    finalCount > 0 ? "partially_calibrated" :
    entries.every((entry) => entry.phase === "unavailable") ? "unavailable" :
    "estimated";
  const activeWorkflow = [...entries].reverse().find(
    (entry) => entry.scope === "workflow" && !isFinal(entry) && entry.phase !== "unavailable",
  );
  return {
    inputTokens,
    outputTokens,
    contextTokens: inputTokens === null ? null : inputTokens + outputTokens,
    outputTokenStatus: calibrationStatus === "provider_final" ? "provider_final" : "characters_divided_by_4",
    cacheReadInputTokens: null,
    tokenLimit: entries.at(-1)?.tokenLimit ?? 2400,
    usageStatus: calibrationStatus === "provider_final" ? "provider_final" : "unavailable",
    preflightInputTokens: inputTokens,
    stablePrefixTokens: null,
    tokenizerStatus: "characters_divided_by_4",
    tokenizer: null,
    promptBreakdown: [],
    calibrationStatus,
    activeWorkflowNodeId: activeWorkflow?.workflowNodeId ?? null,
  };
}
~~~

在发送开始、清除会话、切换 Agent 时清空 usageCalls。对旧服务端事件缺少 usage_key 时使用 chat:default，以保持兼容。事件解析时将 payload.token_limit 保存为 UsageCallState.tokenLimit；事件未携带该字段时才使用 2400。activeWorkflowNodeId 指向最近收到 progress 的未终态 Workflow 调用。

- [ ] **Step 4: 更新 Composer 呈现**

扩展 ContextUsage 类型并替换现有上下文摘要：

~~~
const qualityLabel = {
  estimated: "实时估算",
  partially_calibrated: "部分已校准",
  provider_final: "Provider 已校准",
  unavailable: "Provider 未提供用量",
}[contextUsage.calibrationStatus];
~~~

主视图显示累计 Token 与 qualityLabel；详情继续展示输入、输出、缓存和 prompt breakdown。存在 activeWorkflowNodeId 时追加“当前节点：{id}”。保留原有 tokenizer 说明，且任何 unavailable 状态不得显示为零或“已校准”。

- [ ] **Step 5: 运行前端任务测试**

Run: npm test -- --run components/chat/ChatStore.test.ts components/chat/ChatComposer.test.tsx
Workdir: apps/web
Expected: PASS。

- [ ] **Step 6: 提交 Task 6**

~~~
git add apps/web/stores/chat.ts apps/web/components/chat/ChatComposer.tsx apps/web/components/chat/ChatStore.test.ts apps/web/components/chat/ChatComposer.test.tsx
git commit -m "feat: show cumulative streaming usage status"
~~~

### Task 7: 执行跨层回归、构建与规格验收

**Files:**
- No planned source changes.
- Verify: docs/superpowers/specs/2026-07-19-streaming-usage-and-skill-intent-design.md

**Interfaces:**
- Consumes: Tasks 1-6 的已提交实现。
- Produces: 经验证的三路径实时用量、严格 Skill 意图和兼容的 Workflow 持久化。

- [ ] **Step 1: 运行后端目标回归**

Run: python -m pytest apps/api/tests/test_chat_streaming_skill_creator.py apps/api/tests/test_stream_usage.py apps/api/tests/test_llm_gateway.py apps/api/tests/test_chat_workflow_mode.py apps/api/tests/test_workflow_execution_service.py apps/api/tests/test_context_tokens.py -q
Expected: PASS。

- [ ] **Step 2: 运行前端目标回归**

Run: npm test -- --run components/chat/ChatStore.test.ts components/chat/ChatComposer.test.tsx components/chat/ChatPanel.test.tsx
Workdir: apps/web
Expected: PASS。

- [ ] **Step 3: 运行前端生产构建**

Run: npm run build
Workdir: apps/web
Expected: exit code 0。

- [ ] **Step 4: 按规格逐项验收**

核对下表，并在提交说明中逐项记录证据：

| 规格要求 | 验证证据 |
| --- | --- |
| 非明确请求不创建 Skill | Task 1 的负例与路由无副作用测试 |
| 明确创建 Skill 仍成功 | Task 1 正例与 Task 4 成功路径 |
| 三条路径实时显示估算 | Task 4 和 Task 5 SSE 顺序测试，Task 6 store 测试 |
| Provider 终态校准与 unavailable 明确 | Task 2、Task 4、Task 5、Task 6 测试 |
| Workflow 结果和 NodeRun 兼容 | Task 5 的既有 metadata、Run 和 NodeRun 回归 |

- [ ] **Step 5: 审阅提交差异并报告验收结论**

~~~
git status --short
git diff --check origin/main..HEAD
git log --oneline --decorate -8
~~~

如果任一命令失败，停止 Task 7，回到拥有该行为的 Task 并以新的失败测试定位；不要在最终验收任务中增加未计划的修复。
