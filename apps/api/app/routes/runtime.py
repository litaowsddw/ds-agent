"""Agent Runtime 调试接口。

这些接口用于在项目早期验证 Runtime、Context、Skill、MCP、Memory 等核心抽象。
正式权限体系完成后，本模块所有接口都需要绑定用户和组织权限。
"""

from fastapi import APIRouter

from packages.runtime.agent_runtime import AgentRuntime
from packages.runtime.context_engine import ContextEngine
from packages.runtime.prompt_compiler import PromptContextCompiler

router = APIRouter()


@router.get("/describe")
async def describe_runtime() -> dict[str, object]:
    """返回当前 Agent Runtime 的最小能力描述。"""

    # agent_id 是调试用 Agent 标识，后续会来自数据库中的真实 Agent。
    agent_id = "debug-agent"

    # org_id 是调试用组织标识，后续用于贯穿多租户隔离。
    org_id = "debug-org"

    runtime = AgentRuntime(agent_id=agent_id, org_id=org_id)
    return runtime.describe()


@router.post("/context/assemble")
async def assemble_context(payload: dict[str, object]) -> dict[str, object]:
    """组装一次最小上下文，用于验证 Context Engine 的数据结构。"""

    # token_budget 是本次上下文预算，MVP 阶段使用调用方传入值，后续由模型窗口和策略决定。
    token_budget = int(payload.get("token_budget", 4096))

    # user_input 是当前用户输入，也是上下文 assemble 的动态尾部。
    user_input = str(payload.get("user_input", ""))

    engine = ContextEngine()
    context_bundle = engine.assemble(user_input=user_input, token_budget=token_budget)
    return context_bundle


@router.post("/prompt/compile")
async def compile_prompt(payload: dict[str, object]) -> dict[str, object]:
    """编译 Reasonix 风格的 prefix-cache 友好 Prompt。"""

    compiler = PromptContextCompiler()

    # immutable_prefix 保存稳定前缀片段，字段顺序和内容稳定性直接影响 prefix cache 命中。
    immutable_prefix = payload.get("immutable_prefix", {})

    # append_only_log 保存追加式历史消息，禁止重排和中间改写。
    append_only_log = payload.get("append_only_log", [])

    # current_turn 保存当前回合动态输入，通常放在 Prompt 的最后。
    current_turn = payload.get("current_turn", {})

    return compiler.compile(
        immutable_prefix=immutable_prefix,
        append_only_log=append_only_log,
        current_turn=current_turn,
    )

