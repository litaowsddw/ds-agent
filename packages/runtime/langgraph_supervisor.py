"""基于 LangGraph StateGraph 的 Supervisor Agent。

使用 LangGraph 的 StateGraph 重构 Supervisor 的
plan → delegate → reflect → respond 循环。

图结构：
    START → plan → route_after_plan
      ├─ delegate → reflect → route_after_reflect
      │              ├─ delegate (追加任务)
      │              └─ respond → END
      └─ respond → END (无需子任务的简单问答)

相比旧版 SupervisorAgent：
- 用 LangGraph 条件边替代手写 while 循环
- 用 State 替代 mutable dataclass
- 天然支持 LangSmith 追踪
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from packages.runtime.system_prompt import (
    PLATFORM_AGENT_CONTRACT,
    SUPERVISOR_PLANNING_CONTRACT,
    SUPERVISOR_REFLECTION_CONTRACT,
)

logger = logging.getLogger(__name__)


# ---------- 状态定义 ----------


@dataclass
class SubTaskResult:
    """子任务执行结果。"""
    task: str
    subagent_kind: str
    status: str  # succeeded | failed
    result_text: str
    error_message: str = ""
    tool_calls_made: int = 0


class SupervisorState(TypedDict, total=False):
    """Supervisor StateGraph 的状态。"""
    # 输入
    user_input: str
    org_id: str
    agent_id: str
    workspace_id: str
    available_subagents: list[dict[str, Any]]
    available_tools: list[dict[str, Any]]
    # 规划结果
    intent: str
    reasoning: str
    subtasks: list[dict[str, Any]]  # [{task, subagent_kind, execution_order, depends_on}]
    # 执行结果
    subtask_results: list[SubTaskResult]
    # 反思
    satisfied: bool
    reflection_reasoning: str
    # 迭代控制
    iteration: int
    max_iterations: int
    # 输出
    final_response: str


# ---------- 系统提示词 ----------

PLAN_SYSTEM_PROMPT = """{platform}

{planning}

Available subagent kinds:
- USER_SUB: general assistance
- SYSTEM_SKILL: skill discovery or lifecycle
- SYSTEM_RAG: scoped knowledge retrieval
- SYSTEM_TOOL: enabled external/system tools

Return exactly this JSON object:
{{
  "intent": "intent label",
  "reasoning": "brief evidence-based rationale",
  "subtasks": [
    {{"task": "task", "subagent_kind": "USER_SUB", "execution_order": 0, "depends_on": []}}
  ]
}}""".format(platform=PLATFORM_AGENT_CONTRACT, planning=SUPERVISOR_PLANNING_CONTRACT)

REFLECT_SYSTEM_PROMPT = """{platform}

{reflection}

Return exactly this JSON object:
{{
  "satisfied": true,
  "reasoning": "brief evidence-based assessment",
  "follow_up_tasks": [],
  "final_response": "final user-facing answer when satisfied"
}}""".format(platform=PLATFORM_AGENT_CONTRACT, reflection=SUPERVISOR_REFLECTION_CONTRACT)


# ---------- 规则降级 ----------


def _rule_based_plan(user_input: str, available_subagents: list[dict[str, Any]]) -> dict[str, Any]:
    """基于规则的降级路由。"""
    subtasks: list[dict[str, Any]] = []
    user_input_lower = user_input.lower()

    for subagent in available_subagents:
        kind = subagent.get("kind", "USER_SUB")
        if kind == "SYSTEM_RAG" and any(kw in user_input_lower for kw in ["查找", "搜索", "检索", "知识", "文档", "search", "find"]):
            subtasks.append({"task": user_input, "subagent_kind": "SYSTEM_RAG", "execution_order": 0, "depends_on": []})
        elif kind == "SYSTEM_SKILL" and any(kw in user_input_lower for kw in ["创建技能", "技能", "skill", "create skill"]):
            subtasks.append({"task": user_input, "subagent_kind": "SYSTEM_SKILL", "execution_order": 0, "depends_on": []})

    if not subtasks:
        user_subs = [s for s in available_subagents if s.get("kind") == "USER_SUB"]
        if user_subs:
            subtasks.append({"task": user_input, "subagent_kind": "USER_SUB", "execution_order": 0, "depends_on": []})

    return {
        "intent": "rule_based",
        "reasoning": "规则路由降级",
        "subtasks": subtasks,
    }


# ---------- 节点函数 ----------


async def plan_node(state: SupervisorState, *, chat_model: Any = None) -> dict[str, Any]:
    """规划节点：分析意图、分解任务。"""
    user_input = state.get("user_input", "")
    available_subagents = state.get("available_subagents", [])

    if not chat_model:
        # 无 LLM，规则降级
        result = _rule_based_plan(user_input, available_subagents)
        return {
            "intent": result["intent"],
            "reasoning": result["reasoning"],
            "subtasks": result["subtasks"],
        }

    subagent_descriptions = [
        {"agent_id": s.get("agent_id", ""), "name": s.get("name", ""), "kind": s.get("kind", "USER_SUB"), "description": s.get("description", "")}
        for s in available_subagents
    ]

    plan_prompt = json.dumps({"user_input": user_input, "available_subagents": subagent_descriptions}, ensure_ascii=False)

    try:
        messages = [
            SystemMessage(content=PLAN_SYSTEM_PROMPT),
            HumanMessage(content=plan_prompt),
        ]
        response = await chat_model.ainvoke(messages)
        plan_result = _parse_json_response(response.content)
    except Exception as exc:
        logger.warning(f"LLM 规划失败，降级到规则路由: {exc}")
        result = _rule_based_plan(user_input, available_subagents)
        return {"intent": result["intent"], "reasoning": result["reasoning"], "subtasks": result["subtasks"]}

    if not plan_result:
        result = _rule_based_plan(user_input, available_subagents)
        return {"intent": result["intent"], "reasoning": result["reasoning"], "subtasks": result["subtasks"]}

    return {
        "intent": plan_result.get("intent", "general_query"),
        "reasoning": plan_result.get("reasoning", ""),
        "subtasks": plan_result.get("subtasks", []),
    }


async def delegate_node(state: SupervisorState, *, subagent_executor: Any = None) -> dict[str, Any]:
    """委派节点：执行子任务。"""
    subtasks = state.get("subtasks", [])
    org_id = state.get("org_id", "")
    available_tools = state.get("available_tools", [])
    existing_results: list[SubTaskResult] = list(state.get("subtask_results", []))

    if not subagent_executor:
        for task in subtasks:
            existing_results.append(SubTaskResult(
                task=task.get("task", ""),
                subagent_kind=task.get("subagent_kind", "USER_SUB"),
                status="failed",
                result_text="",
                error_message="Supervisor 未配置真实 SubAgent 执行器",
            ))
        return {"subtask_results": existing_results, "subtasks": []}

    # 按 execution_order 分组执行
    import asyncio
    order_groups: dict[int, list[dict[str, Any]]] = {}
    for task in subtasks:
        order = task.get("execution_order", 0)
        order_groups.setdefault(order, []).append(task)

    for order in sorted(order_groups.keys()):
        group = order_groups[order]
        tasks_coro = [
            subagent_executor(
                task=t.get("task", ""),
                subagent_config=t,
                org_id=org_id,
                available_tools=available_tools,
            )
            for t in group
        ]
        group_results = await asyncio.gather(*tasks_coro, return_exceptions=True)

        for t, r in zip(group, group_results):
            if isinstance(r, Exception):
                existing_results.append(SubTaskResult(
                    task=t.get("task", ""),
                    subagent_kind=t.get("subagent_kind", "USER_SUB"),
                    status="failed",
                    result_text="",
                    error_message=str(r),
                ))
            else:
                existing_results.append(SubTaskResult(
                    task=r.get("task", t.get("task", "")),
                    subagent_kind=r.get("subagent_kind", t.get("subagent_kind", "USER_SUB")),
                    status=r.get("status", "succeeded"),
                    result_text=r.get("result_text", ""),
                    error_message=r.get("error_message", ""),
                    tool_calls_made=r.get("tool_calls_made", 0),
                ))

    return {"subtask_results": existing_results, "subtasks": []}


async def reflect_node(state: SupervisorState, *, chat_model: Any = None) -> dict[str, Any]:
    """反思节点：评估结果，决定是否追加任务。"""
    iteration = state.get("iteration", 0) + 1
    max_iterations = state.get("max_iterations", 3)

    if iteration >= max_iterations:
        return {"satisfied": True, "iteration": iteration, "reflection_reasoning": "达到最大反思轮数"}

    subtask_results = state.get("subtask_results", [])
    if not chat_model or not subtask_results:
        return {"satisfied": True, "iteration": iteration}

    task_results_data = [
        {"task": r.task, "subagent_kind": r.subagent_kind, "status": r.status, "result": r.result_text[:500], "error": r.error_message}
        for r in subtask_results
    ]

    reflect_prompt = json.dumps({
        "user_input": state.get("user_input", ""),
        "intent": state.get("intent", ""),
        "task_results": task_results_data,
        "iteration": iteration,
    }, ensure_ascii=False)

    try:
        messages = [
            SystemMessage(content=REFLECT_SYSTEM_PROMPT),
            HumanMessage(content=reflect_prompt),
        ]
        response = await chat_model.ainvoke(messages)
        reflection = _parse_json_response(response.content)
    except Exception as exc:
        logger.warning(f"反思失败: {exc}")
        return {"satisfied": True, "iteration": iteration, "reflection_reasoning": f"反思失败: {exc}"}

    if not reflection:
        return {"satisfied": True, "iteration": iteration}

    satisfied = reflection.get("satisfied", True)
    result: dict[str, Any] = {
        "satisfied": satisfied,
        "iteration": iteration,
        "reflection_reasoning": reflection.get("reasoning", ""),
    }

    if not satisfied:
        follow_up_tasks = reflection.get("follow_up_tasks", [])
        if follow_up_tasks:
            result["subtasks"] = follow_up_tasks
    else:
        final_response = reflection.get("final_response", "")
        if final_response:
            result["final_response"] = final_response

    return result


def respond_node(state: SupervisorState) -> dict[str, Any]:
    """响应节点：聚合最终结果。"""
    if state.get("final_response"):
        return {}

    subtask_results = state.get("subtask_results", [])
    if not subtask_results:
        return {"final_response": "未能完成任何子任务。"}

    results = []
    for r in subtask_results:
        if r.status == "succeeded":
            results.append(r.result_text)
        else:
            results.append(f"[子任务失败]: {r.error_message}")

    return {"final_response": "\n\n".join(results) if results else "未能完成任何子任务。"}


# ---------- 条件边 ----------


def route_after_plan(state: SupervisorState) -> str:
    """规划后路由：有子任务→delegate，无→respond。"""
    subtasks = state.get("subtasks", [])
    return "delegate" if subtasks else "respond"


def route_after_reflect(state: SupervisorState) -> str:
    """反思后路由：不满意且有追加任务→delegate，满意→respond。"""
    if state.get("satisfied", True):
        return "respond"
    subtasks = state.get("subtasks", [])
    return "delegate" if subtasks else "respond"


# ---------- 图构建 ----------


def create_supervisor_graph(
    chat_model: Any = None,
    subagent_executor: Any = None,
) -> Any:
    """创建 Supervisor LangGraph StateGraph。

    图结构：
        START → plan → route_after_plan
          → delegate → reflect → route_after_reflect
          → respond → END

    参数：
        chat_model: LangChain BaseChatModel 实例（GatewayChatModel）
        subagent_executor: 异步 SubAgent 执行器函数

    返回：
        编译后的 LangGraph 图
    """
    graph = StateGraph(SupervisorState)

    # 使用闭包捕获外部参数
    async def _plan(state: SupervisorState) -> dict[str, Any]:
        return await plan_node(state, chat_model=chat_model)

    async def _delegate(state: SupervisorState) -> dict[str, Any]:
        return await delegate_node(state, subagent_executor=subagent_executor)

    async def _reflect(state: SupervisorState) -> dict[str, Any]:
        return await reflect_node(state, chat_model=chat_model)

    graph.add_node("plan", _plan)
    graph.add_node("delegate", _delegate)
    graph.add_node("reflect", _reflect)
    graph.add_node("respond", respond_node)

    # 边
    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", route_after_plan, {"delegate": "delegate", "respond": "respond"})
    graph.add_edge("delegate", "reflect")
    graph.add_conditional_edges("reflect", route_after_reflect, {"delegate": "delegate", "respond": "respond"})
    graph.add_edge("respond", END)

    return graph.compile()


# ---------- 辅助 ----------


def _parse_json_response(text: str) -> dict[str, Any] | None:
    """解析 LLM 输出的 JSON。"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                return None
        return None
