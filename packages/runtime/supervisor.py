"""Supervisor Agent - 每个 Workspace 的任务规划中枢。

Supervisor Agent 负责：
1. 接收用户消息
2. LLM 意图理解与任务规划
3. 选择 SubAgent 执行子任务
4. 聚合子任务结果
5. 返回最终响应

设计参考 OpenClaw 的 spawn/announce 机制：
- spawn: 创建子 Agent 运行实例
- announce: 向子 Agent 发送消息
- settle: 等待子 Agent 完成并获取结果

v0.3 升级：
- plan() 接入 LLM Gateway 做真正的意图理解和任务分解
- 支持 ReAct 循环：plan → spawn → observe → reflect → plan
- 支持并行子任务和串行子任务
"""

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class TaskStatus(StrEnum):
    """子任务状态。"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SpawnMode(StrEnum):
    """SubAgent 启动模式。"""
    SYNC = "sync"       # 同步等待完成
    ASYNC = "async"     # 异步，后续通过 wake 获取结果
    FIRE_AND_FORGET = "fire_and_forget"  # 触发后不等待


@dataclass(slots=True)
class SubAgentRun:
    """SubAgent 运行实例。"""
    # run_id 是子任务唯一标识
    run_id: str
    # child_session_key 是子 Agent 的会话键
    child_session_key: str
    # requester_session_key 是发起者的会话键
    requester_session_key: str
    # task 是子任务描述
    task: str
    # spawn_mode 是启动模式
    spawn_mode: SpawnMode
    # assigned_subagent_id 是分配的 SubAgent ID
    assigned_subagent_id: str = ""
    # status 是当前状态
    status: TaskStatus = TaskStatus.PENDING
    # frozen_result_text 是子 Agent 完成后的结果文本
    frozen_result_text: str = ""
    # wake_on_descendant_settle 表示是否在子 Agent 完成时唤醒父 Agent
    wake_on_descendant_settle: bool = True
    # error_message 是错误信息
    error_message: str = ""
    # execution_order 是执行顺序（0=并行，1+串行）
    execution_order: int = 0
    # depends_on 是依赖的子任务 ID 列表
    depends_on: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TaskPlan:
    """Supervisor 生成的任务计划。"""
    # plan_id 是计划唯一标识
    plan_id: str
    # original_input 是用户原始输入
    original_input: str
    # intent 是意图识别结果
    intent: str
    # reasoning 是 LLM 推理过程
    reasoning: str = ""
    # subtasks 是子任务列表
    subtasks: list[SubAgentRun] = field(default_factory=list)
    # final_response 是聚合后的最终响应
    final_response: str = ""
    # reflection 是反思结果
    reflection: str = ""
    # iteration 是当前迭代次数
    iteration: int = 0


class LLMCaller(Protocol):
    """LLM 调用协议，Supervisor 通过此协议调用 LLM。"""

    async def call(self, prompt: str, system_prompt: str = "",
                   temperature: float = 0.3, max_tokens: int = 2048) -> str:
        """调用 LLM，返回响应文本。"""


# Supervisor 规划 Prompt 模板
PLAN_SYSTEM_PROMPT = """你是一个任务规划 Supervisor Agent。你的职责是：
1. 分析用户意图
2. 将复杂任务分解为可执行的子任务
3. 为每个子任务分配最合适的 Agent 类型

可用的 SubAgent 类型：
- USER_SUB: 通用对话 Agent，处理常规问题和对话
- SYSTEM_SKILL: Skill Creator，根据描述生成或更新 SKILL.md 技能文件
- SYSTEM_RAG: Knowledge Search，从知识库检索相关文档和片段
- SYSTEM_TOOL: System Tool，执行系统级工具操作

你必须以 JSON 格式输出规划结果，格式如下：
{
  "intent": "意图分类（general_query/knowledge_search/skill_creation/tool_execution/multi_step_task）",
  "reasoning": "你的推理过程",
  "subtasks": [
    {
      "task": "子任务描述",
      "subagent_kind": "USER_SUB|SYSTEM_SKILL|SYSTEM_RAG|SYSTEM_TOOL",
      "spawn_mode": "sync|async",
      "execution_order": 0,
      "depends_on": []
    }
  ]
}

规则：
- 简单问题只需一个 USER_SUB 子任务
- 知识检索使用 SYSTEM_RAG
- 创建/更新技能使用 SYSTEM_SKILL
- 需要按顺序执行的子任务设置递增的 execution_order
- 可并行执行的子任务使用相同 execution_order
- depends_on 列出必须先完成的子任务序号（从0开始）
- 只输出 JSON，不要其他内容"""

REFLECT_SYSTEM_PROMPT = """你是一个反思 Supervisor Agent。评估子任务的执行结果，判断是否需要进一步行动。

你必须以 JSON 格式输出反思结果，格式如下：
{
  "satisfied": true/false,
  "reasoning": "评估推理过程",
  "follow_up_tasks": [
    {
      "task": "后续任务描述",
      "subagent_kind": "USER_SUB|SYSTEM_SKILL|SYSTEM_RAG|SYSTEM_TOOL",
      "spawn_mode": "sync",
      "execution_order": 0,
      "depends_on": []
    }
  ],
  "final_response": "如果 satisfied=true，输出给用户的最终回复"
}

规则：
- 如果所有子任务都成功且结果满足用户需求，设置 satisfied=true
- 如果需要补充信息或重试，设置 satisfied=false 并提供 follow_up_tasks
- 最多进行 3 轮反思
- 只输出 JSON，不要其他内容"""


class SupervisorAgent:
    """Supervisor Agent 核心逻辑。

    每个 Workspace 拥有一个 Supervisor Agent，负责：
    - 解析用户意图（LLM 驱动）
    - 规划子任务（LLM 驱动）
    - 选择合适的 SubAgent 执行
    - 聚合结果
    - 反思并决定是否需要后续行动
    """

    MAX_REFLECTION_ROUNDS = 3

    def __init__(self, agent_id: str, org_id: str, model_provider: str = "mock",
                 model_name: str = "mock-model", llm_caller: LLMCaller | None = None) -> None:
        self.agent_id = agent_id
        self.org_id = org_id
        self.model_provider = model_provider
        self.model_name = model_name
        self.llm_caller = llm_caller
        # 活跃的子任务运行
        self._active_runs: dict[str, SubAgentRun] = {}
        # 规划历史
        self._plan_history: list[TaskPlan] = []

    async def plan(self, user_input: str, available_subagents: list[dict[str, Any]]) -> TaskPlan:
        """根据用户输入规划任务。

        参数：
            user_input: 用户输入文本
            available_subagents: 可用 SubAgent 列表，每个包含 agent_id, name, description, kind

        返回：
            TaskPlan: 任务计划
        """
        # 如果有 LLM 调用器，使用 LLM 做意图理解和任务分解
        if self.llm_caller:
            return await self._llm_plan(user_input, available_subagents)

        # 降级到规则路由
        return self._rule_based_plan(user_input, available_subagents)

    async def reflect(self, plan: TaskPlan) -> TaskPlan:
        """反思当前计划的执行结果，决定是否需要后续行动。

        参数：
            plan: 已执行的计划

        返回：
            更新后的 TaskPlan（可能包含新的子任务）
        """
        if not self.llm_caller:
            return plan

        plan.iteration += 1
        if plan.iteration > self.MAX_REFLECTION_ROUNDS:
            plan.reflection = "达到最大反思轮数，停止进一步行动。"
            return plan

        # 构建反思上下文
        task_results = []
        for subtask in plan.subtasks:
            task_results.append({
                "task": subtask.task,
                "subagent": subtask.assigned_subagent_id,
                "status": subtask.status,
                "result": subtask.frozen_result_text[:500] if subtask.frozen_result_text else "",
                "error": subtask.error_message,
            })

        reflect_prompt = json.dumps({
            "user_input": plan.original_input,
            "intent": plan.intent,
            "task_results": task_results,
            "iteration": plan.iteration,
        }, ensure_ascii=False, indent=2)

        try:
            response_text = await self.llm_caller.call(
                prompt=reflect_prompt,
                system_prompt=REFLECT_SYSTEM_PROMPT,
                temperature=0.2,
            )
            reflection = self._parse_json_response(response_text)
        except Exception as exc:
            plan.reflection = f"反思失败: {exc}"
            return plan

        if not reflection:
            plan.reflection = "反思结果解析失败，停止进一步行动。"
            return plan

        plan.reflection = reflection.get("reasoning", "")

        if reflection.get("satisfied", True):
            plan.final_response = reflection.get("final_response", plan.final_response)
        else:
            # 添加后续任务
            available_subagents = [
                {"agent_id": subtask.assigned_subagent_id, "kind": subtask.assigned_subagent_id.split("_")[1].upper() if "_" in subtask.assigned_subagent_id else "USER_SUB"}
                for subtask in plan.subtasks
            ]
            for follow_up in reflection.get("follow_up_tasks", []):
                subagent = self._find_subagent_by_kind(
                    follow_up.get("subagent_kind", "USER_SUB"), available_subagents
                )
                if subagent:
                    run = SubAgentRun(
                        run_id=f"run_followup_{subagent['agent_id']}_{len(plan.subtasks)}",
                        child_session_key=f"agent:{subagent['agent_id']}:main",
                        requester_session_key=f"agent:{self.agent_id}:main",
                        task=follow_up.get("task", ""),
                        spawn_mode=SpawnMode(follow_up.get("spawn_mode", "sync")),
                        assigned_subagent_id=subagent["agent_id"],
                        execution_order=follow_up.get("execution_order", 0),
                        depends_on=follow_up.get("depends_on", []),
                    )
                    plan.subtasks.append(run)

        return plan

    def spawn(self, subagent_run: SubAgentRun) -> None:
        """启动一个 SubAgent 运行。

        对应 OpenClaw 的 sessions_spawn 语义。
        """
        subagent_run.status = TaskStatus.RUNNING
        self._active_runs[subagent_run.run_id] = subagent_run

    def announce(self, run_id: str, message: str) -> None:
        """向正在运行的 SubAgent 发送消息。

        对应 OpenClaw 的 sessions_send/announce 语义。
        """
        run = self._active_runs.get(run_id)
        if run and run.status == TaskStatus.RUNNING:
            run.task += f"\n[追加消息]: {message}"

    def settle(self, run_id: str, result: str, status: TaskStatus = TaskStatus.SUCCEEDED) -> None:
        """标记 SubAgent 运行完成并冻结结果。

        对应 OpenClaw 的 settle 语义。
        """
        run = self._active_runs.get(run_id)
        if run:
            run.status = status
            run.frozen_result_text = result

    def aggregate(self, plan: TaskPlan) -> str:
        """聚合所有子任务结果，生成最终响应。"""
        results = []
        for subtask in plan.subtasks:
            if subtask.status == TaskStatus.SUCCEEDED:
                results.append(subtask.frozen_result_text)
            elif subtask.status == TaskStatus.FAILED:
                results.append(f"[子任务失败]: {subtask.error_message}")

        if results:
            plan.final_response = "\n\n".join(results)
        else:
            plan.final_response = "未能完成任何子任务。"

        return plan.final_response

    def describe(self) -> dict[str, Any]:
        """返回 Supervisor Agent 的能力描述。"""
        return {
            "agent_id": self.agent_id,
            "org_id": self.org_id,
            "kind": "SUPERVISOR",
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "active_runs": len(self._active_runs),
            "plan_history_count": len(self._plan_history),
            "llm_enabled": self.llm_caller is not None,
        }

    def get_active_runs(self) -> list[SubAgentRun]:
        """返回当前活跃的子任务运行。"""
        return [r for r in self._active_runs.values() if r.status == TaskStatus.RUNNING]

    def get_pending_runs(self) -> list[SubAgentRun]:
        """返回等待执行的子任务（依赖已满足）。"""
        completed_ids = {
            r.run_id for r in self._active_runs.values()
            if r.status in (TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED)
        }
        pending = []
        for r in self._active_runs.values():
            if r.status == TaskStatus.PENDING:
                # 检查依赖是否全部完成
                deps_met = all(dep_id in completed_ids for dep_id in r.depends_on)
                if deps_met:
                    pending.append(r)
        return sorted(pending, key=lambda r: r.execution_order)

    # ---- 内部方法 ----

    async def _llm_plan(self, user_input: str, available_subagents: list[dict[str, Any]]) -> TaskPlan:
        """使用 LLM 进行意图理解和任务分解。"""
        plan = TaskPlan(
            plan_id=f"plan_{self.agent_id}_{id(user_input)}",
            original_input=user_input,
            intent="pending",
        )

        # 构建 LLM 输入
        subagent_descriptions = [
            {"agent_id": s["agent_id"], "name": s.get("name", ""), "kind": s.get("kind", "USER_SUB"), "description": s.get("description", "")}
            for s in available_subagents
        ]

        plan_prompt = json.dumps({
            "user_input": user_input,
            "available_subagents": subagent_descriptions,
        }, ensure_ascii=False, indent=2)

        try:
            response_text = await self.llm_caller.call(
                prompt=plan_prompt,
                system_prompt=PLAN_SYSTEM_PROMPT,
                temperature=0.3,
            )
            plan_result = self._parse_json_response(response_text)
        except Exception as exc:
            # LLM 调用失败，降级到规则路由
            plan.intent = "fallback_rule_based"
            plan.reasoning = f"LLM 规划失败，降级到规则路由: {exc}"
            return self._rule_based_plan(user_input, available_subagents)

        if not plan_result:
            return self._rule_based_plan(user_input, available_subagents)

        plan.intent = plan_result.get("intent", "general_query")
        plan.reasoning = plan_result.get("reasoning", "")

        # 解析 LLM 输出的子任务
        for idx, subtask_data in enumerate(plan_result.get("subtasks", [])):
            kind = subtask_data.get("subagent_kind", "USER_SUB")
            subagent = self._find_subagent_by_kind(kind, available_subagents)
            if subagent:
                run = SubAgentRun(
                    run_id=f"run_{subagent['agent_id']}_{idx}",
                    child_session_key=f"agent:{subagent['agent_id']}:main",
                    requester_session_key=f"agent:{self.agent_id}:main",
                    task=subtask_data.get("task", user_input),
                    spawn_mode=SpawnMode(subtask_data.get("spawn_mode", "sync")),
                    assigned_subagent_id=subagent["agent_id"],
                    execution_order=subtask_data.get("execution_order", 0),
                    depends_on=subtask_data.get("depends_on", []),
                )
                plan.subtasks.append(run)

        # 如果 LLM 没有分配任何子任务，使用默认 USER_SUB
        if not plan.subtasks:
            user_subs = [s for s in available_subagents if s.get("kind") == "USER_SUB"]
            if user_subs:
                subagent = user_subs[0]
                run = SubAgentRun(
                    run_id=f"run_{subagent['agent_id']}_0",
                    child_session_key=f"agent:{subagent['agent_id']}:main",
                    requester_session_key=f"agent:{self.agent_id}:main",
                    task=user_input,
                    spawn_mode=SpawnMode.SYNC,
                    assigned_subagent_id=subagent["agent_id"],
                )
                plan.subtasks.append(run)

        self._plan_history.append(plan)
        return plan

    def _rule_based_plan(self, user_input: str, available_subagents: list[dict[str, Any]]) -> TaskPlan:
        """基于规则的降级路由。"""
        plan = TaskPlan(
            plan_id=f"plan_{self.agent_id}_{id(user_input)}",
            original_input=user_input,
            intent="general_query",
        )

        for subagent in available_subagents:
            kind = subagent.get("kind", "USER_SUB")
            desc = subagent.get("description", "").lower()

            if kind == "SYSTEM_RAG" and any(
                kw in user_input.lower() for kw in ["查找", "搜索", "检索", "知识", "文档"]
            ):
                run = SubAgentRun(
                    run_id=f"run_{subagent['agent_id']}_0",
                    child_session_key=f"agent:{subagent['agent_id']}:main",
                    requester_session_key=f"agent:{self.agent_id}:main",
                    task=user_input,
                    spawn_mode=SpawnMode.SYNC,
                    assigned_subagent_id=subagent["agent_id"],
                )
                plan.subtasks.append(run)

            elif kind == "SYSTEM_SKILL" and any(
                kw in user_input.lower() for kw in ["创建技能", "创建skill", "生成skill", "技能"]
            ):
                run = SubAgentRun(
                    run_id=f"run_{subagent['agent_id']}_0",
                    child_session_key=f"agent:{subagent['agent_id']}:main",
                    requester_session_key=f"agent:{self.agent_id}:main",
                    task=user_input,
                    spawn_mode=SpawnMode.SYNC,
                    assigned_subagent_id=subagent["agent_id"],
                )
                plan.subtasks.append(run)

        if not plan.subtasks:
            user_subs = [s for s in available_subagents if s.get("kind") == "USER_SUB"]
            if user_subs:
                subagent = user_subs[0]
                run = SubAgentRun(
                    run_id=f"run_{subagent['agent_id']}_0",
                    child_session_key=f"agent:{subagent['agent_id']}:main",
                    requester_session_key=f"agent:{self.agent_id}:main",
                    task=user_input,
                    spawn_mode=SpawnMode.SYNC,
                    assigned_subagent_id=subagent["agent_id"],
                )
                plan.subtasks.append(run)

        self._plan_history.append(plan)
        return plan

    def _find_subagent_by_kind(self, kind: str, available_subagents: list[dict[str, Any]]) -> dict[str, Any] | None:
        """根据类型查找可用的 SubAgent。"""
        for subagent in available_subagents:
            if subagent.get("kind") == kind:
                return subagent
        # 如果找不到指定类型，尝试 USER_SUB
        if kind != "USER_SUB":
            for subagent in available_subagents:
                if subagent.get("kind") == "USER_SUB":
                    return subagent
        return None

    def _parse_json_response(self, text: str) -> dict[str, Any] | None:
        """解析 LLM 输出的 JSON。"""
        # 尝试提取 JSON 块
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # 去掉首尾的 ``` 行
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 尝试提取 JSON 对象
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    return None
            return None
