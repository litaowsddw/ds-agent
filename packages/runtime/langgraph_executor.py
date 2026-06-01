"""基于 LangGraph 的 ReAct 执行引擎 — 实现真正的工具调用循环。

核心改进（对比旧版 ExecutionEngine）：
- LLM 可以自主决定调用工具（通过 bind_tools + tool_calls）
- 工具结果自动注入回上下文
- Thought → Action → Observation 循环直到任务完成
- 最大迭代次数保护

图结构：
    START → agent → [有 tool_calls?] → tools → agent (循环)
                      [无 tool_calls] → END
"""

import json
import logging
from typing import Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph

from packages.runtime.langgraph_supervisor import SubTaskResult

logger = logging.getLogger(__name__)


# ---------- ReAct 状态定义 ----------


class ReActState(TypedDict, total=False):
    """ReAct Agent 的 LangGraph 状态。"""
    messages: list[BaseMessage]


# ---------- SubAgent 类型对应的系统提示词 ----------

SUBAGENT_SYSTEM_PROMPTS: dict[str, str] = {
    "SYSTEM_RAG": "你是一个知识检索 Agent。使用 knowledge_search 工具搜索知识库，根据检索结果回答用户问题。",
    "SYSTEM_SKILL": "你是一个技能创建 Agent。使用 skill_create 工具根据用户需求创建技能。",
    "SYSTEM_TOOL": "你是一个系统工具 Agent。使用可用工具完成系统操作任务。",
    "USER_SUB": "你是一个通用对话 Agent。可以使用可用工具辅助回答用户问题。",
}


class LangGraphReActExecutor:
    """基于 LangGraph 的 ReAct 执行引擎。

    支持真正的工具调用循环：
    1. 将工具通过 bind_tools 传给 LLM
    2. LLM 返回 tool_calls 时，自动执行工具
    3. 工具结果注入回消息历史，LLM 继续推理
    4. 循环直到 LLM 不再调用工具或达到最大迭代次数
    """

    def __init__(
        self,
        chat_model: Any = None,
        max_iterations: int = 10,
    ) -> None:
        self.chat_model = chat_model
        self.max_iterations = max_iterations
        self._agent_cache: dict[str, Any] = {}

    async def execute(
        self,
        task: str,
        subagent_kind: str = "USER_SUB",
        tools: list[BaseTool] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """执行一个 SubAgent 任务（ReAct 循环）。

        参数：
            task: 任务描述
            subagent_kind: SubAgent 类型
            tools: 可用的 LangChain 工具列表
            context: 额外上下文

        返回：
            包含 status, result_text, tool_calls_made 等的字典
        """
        tools = tools or []
        system_prompt = SUBAGENT_SYSTEM_PROMPTS.get(subagent_kind, SUBAGENT_SYSTEM_PROMPTS["USER_SUB"])

        # 构建初始消息
        initial_messages: list[BaseMessage] = [
            SystemMessage(content=system_prompt),
        ]
        if context:
            initial_messages.append(SystemMessage(content=f"上下文信息：{json.dumps(context, ensure_ascii=False)}"))
        initial_messages.append(HumanMessage(content=task))

        try:
            agent = self._get_or_create_agent(tools)
            result_state = await agent.ainvoke(
                {"messages": initial_messages},
                config={"recursion_limit": self.max_iterations * 2},
            )

            # 提取最终响应
            messages = result_state.get("messages", [])
            result_text = ""
            tool_calls_made = 0

            for msg in messages:
                if isinstance(msg, AIMessage):
                    if msg.tool_calls:
                        tool_calls_made += len(msg.tool_calls)
                    if msg.content and not msg.tool_calls:
                        result_text = msg.content

            if not result_text and messages:
                last_msg = messages[-1]
                result_text = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

            return {
                "status": "succeeded",
                "result_text": result_text,
                "tool_calls_made": tool_calls_made,
                "subagent_kind": subagent_kind,
                "task": task,
                "error_message": "",
            }

        except Exception as exc:
            logger.error(f"ReAct 执行失败: {exc}")
            return {
                "status": "failed",
                "result_text": "",
                "tool_calls_made": 0,
                "subagent_kind": subagent_kind,
                "task": task,
                "error_message": str(exc),
            }

    def _get_or_create_agent(self, tools: list[BaseTool]) -> Any:
        """创建或获取缓存的 ReAct Agent 图。"""
        tool_names = sorted([t.name for t in tools]) if tools else []
        cache_key = f"{self.chat_model._llm_type if hasattr(self.chat_model, '_llm_type') else 'unknown'}_{'_'.join(tool_names)}"

        if cache_key in self._agent_cache:
            return self._agent_cache[cache_key]

        # 绑定工具到模型
        model_with_tools = self.chat_model.bind_tools(tools) if tools else self.chat_model
        tools_by_name = {tool.name: tool for tool in tools} if tools else {}

        async def agent_node(state: ReActState) -> dict[str, Any]:
            """Agent 节点：调用 LLM，可能返回 tool_calls。"""
            messages = state.get("messages", [])
            response = await model_with_tools.ainvoke(messages)
            return {"messages": messages + [response]}

        async def tools_node(state: ReActState) -> dict[str, Any]:
            """Tools 节点：执行上一个 AIMessage 中的 tool_calls。"""
            messages = state.get("messages", [])
            last_ai_msg = None
            for msg in reversed(messages):
                if isinstance(msg, AIMessage) and msg.tool_calls:
                    last_ai_msg = msg
                    break

            if not last_ai_msg:
                return {"messages": messages}

            new_messages = list(messages)
            for tool_call in last_ai_msg.tool_calls:
                tool_name = tool_call.get("name", "")
                tool_args = tool_call.get("args", {})
                tool_call_id = tool_call.get("id", "")

                tool = tools_by_name.get(tool_name)
                if tool:
                    try:
                        result = await tool.ainvoke(tool_args)
                        new_messages.append(ToolMessage(
                            content=str(result),
                            tool_call_id=tool_call_id,
                            name=tool_name,
                        ))
                    except Exception as exc:
                        new_messages.append(ToolMessage(
                            content=json.dumps({"error": str(exc)}, ensure_ascii=False),
                            tool_call_id=tool_call_id,
                            name=tool_name,
                        ))
                else:
                    new_messages.append(ToolMessage(
                        content=json.dumps({"error": f"未知工具: {tool_name}"}, ensure_ascii=False),
                        tool_call_id=tool_call_id,
                        name=tool_name,
                    ))

            return {"messages": new_messages}

        def should_continue(state: ReActState) -> str:
            """条件边：判断 LLM 是否还想调用工具。"""
            messages = state.get("messages", [])
            if messages:
                last_msg = messages[-1]
                if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
                    return "tools"
            return END

        # 构建图
        graph = StateGraph(ReActState)
        graph.add_node("agent", agent_node)
        graph.add_node("tools", tools_node)
        graph.add_edge(START, "agent")
        graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
        graph.add_edge("tools", "agent")

        agent = graph.compile()
        self._agent_cache[cache_key] = agent
        return agent
