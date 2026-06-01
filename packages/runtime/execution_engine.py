"""SubAgent 执行引擎 - 真正驱动 SubAgent 完成任务。

执行引擎负责：
1. 接收 Supervisor 分配的 SubAgentRun
2. 构建 SubAgent 上下文（system_prompt + task）
3. 通过 LLM Gateway 调用模型
4. 将结果回写到 SubAgentRun
5. 支持同步和异步执行模式

v0.3 新增：
- 对接 LLM Gateway 做真正的 LLM 调用
- 支持 Celery 异步任务执行
- 对接 Context Engine 组装上下文
- 对接 Skill/MCP/Memory 资源
"""

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from packages.runtime.supervisor import SubAgentRun, SpawnMode, TaskStatus


class ExecutionResult:
    """SubAgent 执行结果。"""

    def __init__(self, run_id: str, text: str, status: TaskStatus = TaskStatus.SUCCEEDED,
                 error_message: str = "", usage: dict[str, int] | None = None,
                 artifacts: list[dict[str, Any]] | None = None) -> None:
        self.run_id = run_id
        self.text = text
        self.status = status
        self.error_message = error_message
        self.usage = usage or {}
        self.artifacts = artifacts or []


class LLMCaller(Protocol):
    """LLM 调用协议。"""
    async def call(self, prompt: str, system_prompt: str = "",
                   temperature: float = 0.3, max_tokens: int = 2048) -> str: ...


class ContextProvider(Protocol):
    """上下文提供者协议。"""
    def get_subagent_context(self, agent_id: str, org_id: str) -> dict[str, Any]: ...


class SkillAccessor(Protocol):
    """Skill 访问协议。"""
    def get_skill_summaries(self, agent_id: str, org_id: str) -> list[dict[str, str]]: ...


class MemoryAccessor(Protocol):
    """Memory 访问协议。"""
    def recall_memories(self, org_id: str, agent_id: str, query: str) -> list[dict[str, Any]]: ...


class ToolAccessor(Protocol):
    """MCP Tool 访问协议。"""
    def get_available_tools(self, org_id: str, agent_id: str) -> list[dict[str, Any]]: ...


class ResultCallback(Protocol):
    """结果回调协议。"""
    async def on_result(self, result: ExecutionResult) -> None: ...


class SubAgentExecutionEngine:
    """SubAgent 执行引擎。

    负责真正驱动 SubAgent 完成任务，包括：
    - 构建 SubAgent 的完整上下文
    - 调用 LLM 生成响应
    - 支持工具调用（Skill、MCP Tool）
    - 管理执行状态
    """

    def __init__(
        self,
        llm_caller: LLMCaller | None = None,
        context_provider: ContextProvider | None = None,
        skill_accessor: SkillAccessor | None = None,
        memory_accessor: MemoryAccessor | None = None,
        tool_accessor: ToolAccessor | None = None,
        result_callback: ResultCallback | None = None,
    ) -> None:
        self.llm_caller = llm_caller
        self.context_provider = context_provider
        self.skill_accessor = skill_accessor
        self.memory_accessor = memory_accessor
        self.tool_accessor = tool_accessor
        self.result_callback = result_callback

        # 执行历史
        self._execution_history: list[ExecutionResult] = []

    async def execute(self, run: SubAgentRun, org_id: str) -> ExecutionResult:
        """执行一个 SubAgent 任务。

        参数：
            run: SubAgent 运行实例
            org_id: 组织 ID

        返回：
            ExecutionResult: 执行结果
        """
        if not self.llm_caller:
            # 没有配置 LLM 调用器，返回 mock 结果
            result = ExecutionResult(
                run_id=run.run_id,
                text=f"[SubAgent 执行] {run.task}",
                status=TaskStatus.SUCCEEDED,
                usage={"prompt_tokens": 0, "completion_tokens": 0},
            )
            run.status = TaskStatus.SUCCEEDED
            run.frozen_result_text = result.text
            self._execution_history.append(result)
            return result

        try:
            # 1. 构建 SubAgent 上下文
            context = self._build_context(run, org_id)

            # 2. 召回相关记忆
            memories = []
            if self.memory_accessor:
                memories = self.memory_accessor.recall_memories(org_id, run.assigned_subagent_id, run.task)

            # 3. 获取可用 Skill
            skills = []
            if self.skill_accessor:
                skills = self.skill_accessor.get_skill_summaries(run.assigned_subagent_id, org_id)

            # 4. 获取可用工具
            tools = []
            if self.tool_accessor:
                tools = self.tool_accessor.get_available_tools(org_id, run.assigned_subagent_id)

            # 5. 组装完整 Prompt
            prompt = self._assemble_prompt(run, context, memories, skills, tools)
            system_prompt = context.get("system_prompt", "")

            # 6. 调用 LLM
            response_text = await self.llm_caller.call(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.3,
            )

            # 7. 构建执行结果
            result = ExecutionResult(
                run_id=run.run_id,
                text=response_text,
                status=TaskStatus.SUCCEEDED,
            )

            # 8. 更新运行状态
            run.status = TaskStatus.SUCCEEDED
            run.frozen_result_text = response_text

        except Exception as exc:
            result = ExecutionResult(
                run_id=run.run_id,
                text="",
                status=TaskStatus.FAILED,
                error_message=str(exc),
            )
            run.status = TaskStatus.FAILED
            run.error_message = str(exc)

        # 记录执行历史
        self._execution_history.append(result)

        # 通知结果回调
        if self.result_callback:
            await self.result_callback.on_result(result)

        return result

    async def execute_sync(self, runs: list[SubAgentRun], org_id: str) -> list[ExecutionResult]:
        """同步执行一组 SubAgent 任务（按 execution_order 排序）。

        同一 execution_order 的任务并行执行，不同 order 的串行执行。
        """
        results: list[ExecutionResult] = []

        # 按 execution_order 分组
        order_groups: dict[int, list[SubAgentRun]] = {}
        for run in runs:
            order = run.execution_order
            if order not in order_groups:
                order_groups[order] = []
            order_groups[order].append(run)

        # 按顺序执行每组
        for order in sorted(order_groups.keys()):
            group_runs = order_groups[order]
            # 同组并行执行
            import asyncio
            group_results = await asyncio.gather(*[
                self.execute(run, org_id) for run in group_runs
            ])
            results.extend(group_results)

            # 检查是否有失败的任务，决定是否继续
            failed = [r for r in group_results if r.status == TaskStatus.FAILED]
            if failed and any(run.spawn_mode == SpawnMode.SYNC for run in group_runs):
                # 同步模式下，如果有失败，取消后续任务
                for later_order in sorted(order_groups.keys()):
                    if later_order > order:
                        for later_run in order_groups[later_order]:
                            later_run.status = TaskStatus.CANCELLED
                            results.append(ExecutionResult(
                                run_id=later_run.run_id,
                                text="",
                                status=TaskStatus.CANCELLED,
                                error_message="前置任务失败，取消执行",
                            ))
                break

        return results

    def get_execution_history(self) -> list[ExecutionResult]:
        """返回执行历史。"""
        return list(self._execution_history)

    # ---- 内部方法 ----

    def _build_context(self, run: SubAgentRun, org_id: str) -> dict[str, Any]:
        """构建 SubAgent 上下文。"""
        if self.context_provider:
            return self.context_provider.get_subagent_context(run.assigned_subagent_id, org_id)

        # 默认上下文
        return {
            "agent_id": run.assigned_subagent_id,
            "system_prompt": "你是一个 AI Agent，帮助用户完成任务。",
        }

    def _assemble_prompt(
        self,
        run: SubAgentRun,
        context: dict[str, Any],
        memories: list[dict[str, Any]],
        skills: list[dict[str, str]],
        tools: list[dict[str, Any]],
    ) -> str:
        """组装完整的 LLM Prompt。"""
        parts: list[str] = []

        # 任务描述
        parts.append(f"## 任务\n{run.task}")

        # 可用 Skill
        if skills:
            parts.append("## 可用 Skill")
            for skill in skills:
                parts.append(f"- {skill.get('name', '')} [{skill.get('scope', '')}]: {skill.get('description', '')}")

        # 召回的记忆
        if memories:
            parts.append("## 相关记忆")
            for memory in memories:
                parts.append(f"- [{memory.get('memory_type', 'memory')}] {memory.get('summary', '')}")

        # 可用工具
        if tools:
            parts.append("## 可用工具")
            for tool in tools:
                parts.append(f"- {tool.get('name', '')}: {tool.get('description', '')}")

        # 提示
        parts.append("## 输出要求\n请直接完成任务并输出结果。")

        return "\n\n".join(parts)
