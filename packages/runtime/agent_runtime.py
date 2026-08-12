"""Agent Runtime 核心对象。

AgentRuntime 是每个 Agent 的运行时门面，API、Workflow Worker、后台 Agent
都应该通过它访问上下文、Skill、MCP、Memory 等能力。

v0.4 — LangGraph + LangChain 单一执行路径：
- Supervisor 使用 LangGraph StateGraph（plan → delegate → reflect → respond）
- SubAgent 使用 LangGraph ReAct Agent（支持真正的工具调用循环）
- LLM 调用通过 GatewayChatModel 桥接到 LLMGateway
- 工具（MCP/RAG/Skill/Memory）包装为 LangChain BaseTool
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from packages.runtime.subagent import SubAgentRegistry, AgentKind, create_system_subagents

logger = logging.getLogger(__name__)


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

    # enabled_capabilities
    enabled_capabilities: list[str] = field(
        default_factory=lambda: [
            "workspace", "session", "context", "skill", "mcp", "memory",
            "prompt_compiler", "background_agent", "supervisor", "subagent",
            "a2a", "evolver",
        ]
    )

    # SubAgent 注册表
    subagent_registry: SubAgentRegistry | None = None

    # LangGraph 组件
    langgraph_chat_model: Any = None  # GatewayChatModel
    langgraph_executor: Any = None    # LangGraphReActExecutor
    langgraph_supervisor_graph: Any = None  # 编译后的 Supervisor StateGraph

    # LLM 调用器（普通 Agent 直接对话路径）
    llm_caller: Any = None  # LLMCaller | None

    # 已由 API/A2A 边界编译的稳定平台提示词。直接对话也必须带上它，
    # 不能因为没有进入流式聊天路径而退化为裸用户输入。
    system_prompt: str = ""

    # 已注入且已经过 Agent 范围授权的可执行系统工具。运行时不根据
    # 名称猜测能力；调用方必须显式提供这些 BaseTool 实例。
    system_tools: list[Any] = field(default_factory=list)

    # 数据库访问器
    db_accessor: Any = None  # DBAccessor | None

    def init_supervisor(self, chat_model: Any, llm_caller: Any = None) -> None:
        """初始化 Supervisor 模式。

        参数：
            chat_model: LangChain BaseChatModel（GatewayChatModel）。Supervisor 的
                plan/reflect 和 SubAgent ReAct 循环都依赖它，必须真实提供。
            llm_caller: 兼容用途的文本调用器（可选）。
        """
        self.kind = AgentKind.SUPERVISOR
        self.llm_caller = llm_caller
        self.langgraph_chat_model = chat_model

        self.subagent_registry = SubAgentRegistry()
        self._init_langgraph_components()

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
                tools=list(self.system_tools),
            )

        # Supervisor StateGraph
        self.langgraph_supervisor_graph = create_supervisor_graph(
            chat_model=self.langgraph_chat_model,
            subagent_executor=subagent_executor,
        )

    async def chat(self, user_input: str, session_id: str | None = None) -> dict[str, Any]:
        """处理用户输入，返回响应。"""
        if self.kind == AgentKind.SUPERVISOR and self.langgraph_supervisor_graph:
            return await self._supervisor_chat(user_input, session_id)
        return await self._direct_chat(user_input, session_id)

    async def _supervisor_chat(self, user_input: str, session_id: str | None = None) -> dict[str, Any]:
        """Supervisor 模式：plan → delegate → reflect → respond。"""
        available_subagents = (
            self.subagent_registry.list_available_for_supervisor() if self.subagent_registry else []
        )

        if self.db_accessor and self.workspace_id:
            try:
                db_subagents = await self.db_accessor.list_subagents(self.workspace_id, self.org_id)
                for sa in db_subagents:
                    if sa.get("agent_id") != self.agent_id:
                        available_subagents.append(sa)
            except Exception as exc:
                logger.warning("加载工作区 SubAgent 失败，使用内置注册表: %s", exc)

        initial_state = {
            "user_input": user_input,
            "org_id": self.org_id,
            "agent_id": self.agent_id,
            "workspace_id": self.workspace_id,
            "available_subagents": available_subagents,
            "available_tools": [
                {"name": tool.name, "description": tool.description}
                for tool in self.system_tools
            ],
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
            except Exception as exc:
                logger.warning("保存会话消息失败: %s", exc)

        return {
            "response": final_response,
            "intent": result_state.get("intent", ""),
            "subtask_count": len(subtask_results),
            "succeeded_count": len([r for r in subtask_results if r.status == "succeeded"]),
            "failed_count": len([r for r in subtask_results if r.status == "failed"]),
            "reflection_rounds": result_state.get("iteration", 0),
            "runtime_mode": "langgraph",
        }

    async def _direct_chat(self, user_input: str, session_id: str | None = None) -> dict[str, Any]:
        """普通 Agent 直接调用 LLM。"""
        if not self.llm_caller:
            return {"error": "Agent 未配置真实 LLM 调用器", "mode": "error"}

        try:
            if self.system_prompt:
                system_prompt = self.system_prompt
            else:
                from packages.runtime.system_prompt import build_agent_system_prompt

                system_prompt = build_agent_system_prompt(agent_name="Agent")
            response_text = await self.llm_caller.call(
                prompt=user_input,
                system_prompt=system_prompt,
                temperature=0.3,
            )

            if self.db_accessor and session_id:
                try:
                    await self.db_accessor.save_message(session_id, "user", user_input)
                    await self.db_accessor.save_message(session_id, "assistant", response_text)
                except Exception as exc:
                    logger.warning("保存会话消息失败: %s", exc)

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
        }

        result: dict[str, Any] = {
            "runtime_scope": runtime_scope,
            "enabled_capabilities": self.enabled_capabilities,
            "system_tools": [
                {"name": tool.name, "description": tool.description}
                for tool in self.system_tools
            ],
        }

        if self.subagent_registry:
            result["subagents"] = self.subagent_registry.list_available_for_supervisor()

        return result
