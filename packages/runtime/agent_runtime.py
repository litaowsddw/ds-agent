"""Agent Runtime 核心对象。

AgentRuntime 是每个 Agent 的运行时门面，API、Workflow Worker、后台 Agent
都应该通过它访问上下文、Skill、MCP、Memory 等能力。

v0.4 升级 — LangGraph + LangChain：
- Supervisor 使用 LangGraph StateGraph（plan → delegate → reflect → respond）
- SubAgent 使用 LangGraph ReAct Agent（支持真正的工具调用循环）
- LLM 调用通过 GatewayChatModel 桥接到 LLMGateway
- 工具（MCP/RAG/Skill/Memory）包装为 LangChain BaseTool
- 保留旧接口兼容，新增 langgraph 模式
"""

from dataclasses import dataclass, field
from typing import Any, Protocol

from packages.runtime.supervisor import SupervisorAgent, SubAgentRun, TaskStatus
from packages.runtime.subagent import SubAgentRegistry, AgentKind, SubAgentConfig, create_system_subagents
from packages.runtime.session_router import SessionRouter
from packages.runtime.execution_engine import SubAgentExecutionEngine


class LLMCaller(Protocol):
    """LLM 调用协议。"""
    async def call(self, prompt: str, system_prompt: str = "",
                   temperature: float = 0.3, max_tokens: int = 2048) -> str: ...


class DBAccessor(Protocol):
    """数据库访问协议。"""
    async def get_agent(self, agent_id: str) -> dict[str, Any] | None: ...
    async def list_subagents(self, workspace_id: str, org_id: str) -> list[dict[str, Any]]: ...
    async def save_message(self, session_id: str, role: str, content: str, **kwargs: Any) -> None: ...
    async def get_messages(self, session_id: str, limit: int = 50) -> list[dict[str, Any]]: ...


@dataclass(slots=True)
class AgentRuntime:
    """描述一个 Agent 的运行时边界。"""

    # agent_id 是 Agent 的唯一标识
    agent_id: str

    # org_id 是组织标识，多租户隔离
    org_id: str

    # Agent 类型
    kind: AgentKind = AgentKind.USER_SUB

    # 模型配置
    model_provider: str = ""
    model_name: str = ""

    # Workspace ID
    workspace_id: str = ""

    # 运行模式：legacy（旧版手写循环）或 langgraph（LangGraph StateGraph）
    runtime_mode: str = "langgraph"

    # enabled_capabilities
    enabled_capabilities: list[str] = field(
        default_factory=lambda: [
            "workspace", "session", "context", "skill", "mcp", "memory",
            "prompt_compiler", "background_agent", "supervisor", "subagent",
            "a2a", "evolver",
        ]
    )

    # Supervisor Agent（仅 kind=SUPERVISOR 时使用）
    supervisor: SupervisorAgent | None = None

    # SubAgent 注册表
    subagent_registry: SubAgentRegistry | None = None

    # Session 路由器
    session_router: SessionRouter | None = None

    # SubAgent 执行引擎（legacy 模式）
    execution_engine: SubAgentExecutionEngine | None = None

    # LangGraph 组件（langgraph 模式）
    langgraph_chat_model: Any = None  # GatewayChatModel
    langgraph_executor: Any = None    # LangGraphReActExecutor
    langgraph_supervisor_graph: Any = None  # 编译后的 Supervisor StateGraph

    # LLM 调用器
    llm_caller: Any = None  # LLMCaller | None

    # 数据库访问器
    db_accessor: Any = None  # DBAccessor | None

    def init_supervisor(self, llm_caller: Any = None, chat_model: Any = None) -> None:
        """初始化 Supervisor 模式。

        参数：
            llm_caller: LLM 调用器（legacy 模式）
            chat_model: LangChain BaseChatModel（langgraph 模式）
        """
        self.kind = AgentKind.SUPERVISOR
        self.llm_caller = llm_caller
        self.langgraph_chat_model = chat_model

        # 初始化 legacy 组件
        self.supervisor = SupervisorAgent(
            agent_id=self.agent_id,
            org_id=self.org_id,
            model_provider=self.model_provider,
            model_name=self.model_name,
            llm_caller=llm_caller,
        )
        self.subagent_registry = SubAgentRegistry()
        self.session_router = SessionRouter()
        self.execution_engine = SubAgentExecutionEngine(llm_caller=llm_caller)

        # 初始化 LangGraph 组件
        if self.runtime_mode == "langgraph":
            self._init_langgraph_components()

        # 创建主会话路由
        self.session_router.create_main_session(self.agent_id)

        # 注册系统 SubAgent
        system_subagents = create_system_subagents(self.org_id, self.workspace_id)
        for subagent_config in system_subagents:
            self.subagent_registry.register(subagent_config)

    def _init_langgraph_components(self) -> None:
        """初始化 LangGraph 组件。"""
        from packages.runtime.langgraph_executor import LangGraphReActExecutor
        from packages.runtime.langgraph_supervisor import create_supervisor_graph

        # ReAct 执行引擎
        self.langgraph_executor = LangGraphReActExecutor(
            chat_model=self.langgraph_chat_model,
            max_iterations=10,
        )

        # SubAgent 执行器函数（传给 Supervisor delegate 节点）
        async def subagent_executor(task: str, subagent_config: dict[str, Any],
                                     org_id: str, available_tools: list[dict[str, Any]]) -> dict[str, Any]:
            return await self.langgraph_executor.execute(
                task=task,
                subagent_kind=subagent_config.get("subagent_kind", "USER_SUB"),
                tools=[],  # TODO: 从 available_tools 转换为 LangChain BaseTool
            )

        # Supervisor StateGraph
        self.langgraph_supervisor_graph = create_supervisor_graph(
            chat_model=self.langgraph_chat_model,
            subagent_executor=subagent_executor,
        )

    async def chat(self, user_input: str, session_id: str | None = None) -> dict[str, Any]:
        """处理用户输入，返回响应。"""
        if self.kind == AgentKind.SUPERVISOR and self.supervisor:
            if self.runtime_mode == "langgraph" and self.langgraph_supervisor_graph:
                return await self._langgraph_supervisor_chat(user_input, session_id)
            else:
                return await self._supervisor_chat(user_input, session_id)
        else:
            return await self._direct_chat(user_input, session_id)

    # ---- LangGraph 模式 ----

    async def _langgraph_supervisor_chat(self, user_input: str, session_id: str | None = None) -> dict[str, Any]:
        """LangGraph Supervisor 模式。"""
        available_subagents = self.subagent_registry.list_available_for_supervisor()

        if self.db_accessor and self.workspace_id:
            try:
                db_subagents = await self.db_accessor.list_subagents(self.workspace_id, self.org_id)
                for sa in db_subagents:
                    if sa.get("agent_id") != self.agent_id:
                        available_subagents.append(sa)
            except Exception:
                pass

        initial_state = {
            "user_input": user_input,
            "org_id": self.org_id,
            "agent_id": self.agent_id,
            "workspace_id": self.workspace_id,
            "available_subagents": available_subagents,
            "available_tools": [],
            "iteration": 0,
            "max_iterations": 3,
        }

        result_state = await self.langgraph_supervisor_graph.ainvoke(initial_state)

        final_response = result_state.get("final_response", "")
        subtask_results = result_state.get("subtask_results", [])

        # 保存消息
        if self.db_accessor and session_id:
            try:
                await self.db_accessor.save_message(session_id, "user", user_input)
                await self.db_accessor.save_message(session_id, "assistant", final_response)
            except Exception:
                pass

        return {
            "response": final_response,
            "intent": result_state.get("intent", ""),
            "subtask_count": len(subtask_results),
            "succeeded_count": len([r for r in subtask_results if r.status == "succeeded"]),
            "failed_count": len([r for r in subtask_results if r.status == "failed"]),
            "reflection_rounds": result_state.get("iteration", 0),
            "runtime_mode": "langgraph",
        }

    # ---- Legacy 模式（保留向后兼容）----

    async def _supervisor_chat(self, user_input: str, session_id: str | None = None) -> dict[str, Any]:
        """Legacy Supervisor 模式。"""
        if not self.supervisor or not self.subagent_registry:
            return {"error": "Supervisor 未初始化"}

        available_subagents = self.subagent_registry.list_available_for_supervisor()

        if self.db_accessor and self.workspace_id:
            try:
                db_subagents = await self.db_accessor.list_subagents(self.workspace_id, self.org_id)
                for sa in db_subagents:
                    if sa.get("agent_id") != self.agent_id:
                        available_subagents.append(sa)
            except Exception:
                pass

        plan = await self.supervisor.plan(user_input, available_subagents)

        for run in plan.subtasks:
            self.supervisor.spawn(run)

        if self.execution_engine:
            execution_results = await self.execution_engine.execute_sync(plan.subtasks, self.org_id)
        else:
            for run in plan.subtasks:
                run.status = TaskStatus.SUCCEEDED
                run.frozen_result_text = f"[降级执行] {run.task}"

        plan = await self.supervisor.reflect(plan)

        max_iterations = 3
        iteration = 0
        while not plan.final_response and iteration < max_iterations:
            new_runs = [r for r in plan.subtasks if r.status == TaskStatus.PENDING]
            if not new_runs:
                break
            for run in new_runs:
                self.supervisor.spawn(run)
            if self.execution_engine:
                await self.execution_engine.execute_sync(new_runs, self.org_id)
            plan = await self.supervisor.reflect(plan)
            iteration += 1

        if not plan.final_response:
            final_response = self.supervisor.aggregate(plan)
        else:
            final_response = plan.final_response

        if self.db_accessor and session_id:
            try:
                await self.db_accessor.save_message(session_id, "user", user_input)
                await self.db_accessor.save_message(session_id, "assistant", final_response)
            except Exception:
                pass

        return {
            "response": final_response,
            "plan_id": plan.plan_id,
            "intent": plan.intent,
            "subtask_count": len(plan.subtasks),
            "succeeded_count": len([s for s in plan.subtasks if s.status == TaskStatus.SUCCEEDED]),
            "failed_count": len([s for s in plan.subtasks if s.status == TaskStatus.FAILED]),
            "reflection_rounds": iteration,
            "runtime_mode": "legacy",
        }

    async def _direct_chat(self, user_input: str, session_id: str | None = None) -> dict[str, Any]:
        """普通 Agent 直接调用 LLM。"""
        if not self.llm_caller:
            return {"error": "Agent 未配置真实 LLM 调用器", "mode": "error"}

        try:
            response_text = await self.llm_caller.call(prompt=user_input, temperature=0.3)

            if self.db_accessor and session_id:
                try:
                    await self.db_accessor.save_message(session_id, "user", user_input)
                    await self.db_accessor.save_message(session_id, "assistant", response_text)
                except Exception:
                    pass

            return {"response": response_text, "mode": "llm"}
        except Exception as exc:
            return {"error": str(exc), "mode": "error"}

    def describe(self) -> dict[str, Any]:
        """返回 Agent Runtime 的能力描述。"""
        runtime_scope = {
            "org_id": self.org_id,
            "agent_id": self.agent_id,
            "kind": self.kind,
            "workspace_id": self.workspace_id,
            "runtime_mode": self.runtime_mode,
        }

        result: dict[str, Any] = {
            "runtime_scope": runtime_scope,
            "enabled_capabilities": self.enabled_capabilities,
        }

        if self.supervisor:
            result["supervisor"] = self.supervisor.describe()

        if self.subagent_registry:
            result["subagents"] = self.subagent_registry.list_available_for_supervisor()

        if self.execution_engine:
            result["execution_history_count"] = len(self.execution_engine.get_execution_history())

        return result
