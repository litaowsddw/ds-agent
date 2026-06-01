"""LangGraph Agent 重构的单元测试。

测试覆盖：
1. 消息格式转换
2. ReAct Agent 工具调用循环
3. Supervisor StateGraph 完整流程
4. LangChain Tool 包装器
"""

import asyncio
import json
import pytest


# ─── 消息格式转换测试 ───


class TestMessagesToPrompt:
    """测试 LangChain 消息 → 文本 prompt 转换。"""

    def test_basic_conversion(self):
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
        from packages.runtime.langchain_gateway import _messages_to_prompt

        messages = [
            SystemMessage(content="You are a helpful assistant."),
            HumanMessage(content="Hello!"),
            AIMessage(content="Hi there!"),
        ]
        result = _messages_to_prompt(messages)

        assert "[System]" in result
        assert "You are a helpful assistant." in result
        assert "[User]" in result
        assert "Hello!" in result
        assert "[Assistant]" in result
        assert "Hi there!" in result

    def test_tool_call_conversion(self):
        from langchain_core.messages import AIMessage, HumanMessage
        from packages.runtime.langchain_gateway import _messages_to_prompt

        messages = [
            HumanMessage(content="Search for Python"),
            AIMessage(
                content="",
                tool_calls=[{"name": "knowledge_search", "args": {"query": "Python"}, "id": "call_1", "type": "tool_call"}],
            ),
        ]
        result = _messages_to_prompt(messages)
        assert "[Assistant-ToolCall]" in result
        assert "knowledge_search" in result

    def test_tool_message_conversion(self):
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
        from packages.runtime.langchain_gateway import _messages_to_prompt

        messages = [
            HumanMessage(content="Search"),
            AIMessage(content="", tool_calls=[{"name": "search", "args": {"q": "test"}, "id": "c1", "type": "tool_call"}]),
            ToolMessage(content="Found results", tool_call_id="c1", name="search"),
        ]
        result = _messages_to_prompt(messages)
        assert "[Tool-search]" in result
        assert "Found results" in result


# ─── GatewayChatModel 测试 ───


class TestGatewayChatModel:
    """测试 GatewayChatModel 桥接层。"""

    def test_llm_type(self):
        from packages.runtime.langchain_gateway import GatewayChatModel

        model = GatewayChatModel(provider="openai", model="gpt-4o")
        assert model._llm_type == "gateway-openai"

    def test_bind_tools(self):
        from packages.runtime.langchain_gateway import GatewayChatModel
        from packages.runtime.tools.rag_tool import RAGSearchTool

        async def mock_rag(query, collection, top_k, org_id, agent_id):
            return []

        model = GatewayChatModel(provider="openai", model="gpt-4o")
        rag_tool = RAGSearchTool(org_id="org_1", agent_id="agent_1", rag_executor=mock_rag)
        bound = model.bind_tools([rag_tool])

        assert len(bound.bound_tools) == 1
        assert bound.bound_tools[0]["function"]["name"] == "knowledge_search"


# ─── LangChain Tool 包装器测试 ───


class TestLangChainTools:
    """测试各 Tool 包装器。"""

    @pytest.mark.asyncio
    async def test_rag_tool(self):
        from packages.runtime.tools.rag_tool import RAGSearchTool

        async def mock_rag(query, collection, top_k, org_id, agent_id):
            return [{"content": f"About {query}", "score": 0.9}]

        tool = RAGSearchTool(org_id="org_1", agent_id="agent_1", rag_executor=mock_rag)
        result = await tool.ainvoke({"query": "Python", "collection": "default"})
        data = json.loads(result)
        assert len(data) == 1
        assert "Python" in data[0]["content"]

    @pytest.mark.asyncio
    async def test_memory_tool(self):
        from packages.runtime.tools.memory_tool import MemoryRecallTool

        async def mock_memory(query, org_id, agent_id, top_k):
            return [{"role": "user", "content": "test memory"}]

        tool = MemoryRecallTool(org_id="org_1", agent_id="agent_1", memory_accessor=mock_memory)
        result = await tool.ainvoke({"query": "test"})
        data = json.loads(result)
        assert len(data) == 1

    @pytest.mark.asyncio
    async def test_skill_tool(self):
        from packages.runtime.tools.skill_tool import SkillCreatorTool

        async def mock_skill(name, description, instructions, org_id, agent_id):
            return {"skill_id": "s1", "name": name, "status": "created"}

        tool = SkillCreatorTool(org_id="org_1", agent_id="agent_1", skill_accessor=mock_skill)
        result = await tool.ainvoke({"name": "test_skill", "description": "A test skill"})
        data = json.loads(result)
        assert data["status"] == "created"

    @pytest.mark.asyncio
    async def test_mcp_tool_no_accessor(self):
        from packages.runtime.tools.mcp_tools import MCPTool

        tool = MCPTool(name="test_mcp", org_id="org_1", agent_id="agent_1")
        result = await tool.ainvoke({})
        data = json.loads(result)
        assert "error" in data


# ─── Supervisor StateGraph 测试 ───


class TestSupervisorStateGraph:
    """测试 Supervisor LangGraph StateGraph。"""

    def test_rule_based_plan_rag(self):
        from packages.runtime.langgraph_supervisor import _rule_based_plan

        result = _rule_based_plan("搜索Python文档", [
            {"agent_id": "rag_1", "kind": "SYSTEM_RAG", "name": "RAG"},
        ])
        assert result["intent"] == "rule_based"
        assert len(result["subtasks"]) == 1
        assert result["subtasks"][0]["subagent_kind"] == "SYSTEM_RAG"

    def test_rule_based_plan_general(self):
        from packages.runtime.langgraph_supervisor import _rule_based_plan

        result = _rule_based_plan("你好", [
            {"agent_id": "sub_1", "kind": "USER_SUB", "name": "General"},
        ])
        assert len(result["subtasks"]) == 1
        assert result["subtasks"][0]["subagent_kind"] == "USER_SUB"

    def test_route_after_plan(self):
        from packages.runtime.langgraph_supervisor import route_after_plan

        assert route_after_plan({"subtasks": [{"task": "t1"}]}) == "delegate"
        assert route_after_plan({"subtasks": []}) == "respond"

    def test_route_after_reflect(self):
        from packages.runtime.langgraph_supervisor import route_after_reflect

        assert route_after_reflect({"satisfied": True}) == "respond"
        assert route_after_reflect({"satisfied": False, "subtasks": [{"task": "t1"}]}) == "delegate"
        assert route_after_reflect({"satisfied": False, "subtasks": []}) == "respond"

    @pytest.mark.asyncio
    async def test_plan_node_no_llm(self):
        from packages.runtime.langgraph_supervisor import plan_node

        state = {
            "user_input": "搜索知识",
            "available_subagents": [{"agent_id": "rag_1", "kind": "SYSTEM_RAG"}],
        }
        result = await plan_node(state, chat_model=None)
        assert result["intent"] == "rule_based"
        assert len(result["subtasks"]) >= 1

    @pytest.mark.asyncio
    async def test_delegate_node_mock(self):
        from packages.runtime.langgraph_supervisor import delegate_node

        async def mock_executor(task, subagent_config, org_id, available_tools):
            return {
                "task": task,
                "subagent_kind": subagent_config.get("subagent_kind", "USER_SUB"),
                "status": "succeeded",
                "result_text": f"Result: {task}",
                "error_message": "",
                "tool_calls_made": 0,
            }

        state = {
            "subtasks": [{"task": "search", "subagent_kind": "SYSTEM_RAG", "execution_order": 0}],
            "org_id": "org_1",
            "available_tools": [],
            "subtask_results": [],
        }
        result = await delegate_node(state, subagent_executor=mock_executor)
        assert len(result["subtask_results"]) == 1
        assert result["subtask_results"][0].status == "succeeded"

    @pytest.mark.asyncio
    async def test_respond_node(self):
        from packages.runtime.langgraph_supervisor import respond_node, SubTaskResult

        state = {
            "subtask_results": [
                SubTaskResult(task="t1", subagent_kind="USER_SUB", status="succeeded", result_text="Done t1"),
                SubTaskResult(task="t2", subagent_kind="SYSTEM_RAG", status="succeeded", result_text="Found docs"),
            ]
        }
        result = respond_node(state)
        assert "Done t1" in result["final_response"]
        assert "Found docs" in result["final_response"]

    @pytest.mark.asyncio
    async def test_supervisor_full_loop(self):
        from packages.runtime.langgraph_supervisor import create_supervisor_graph

        async def mock_subagent_executor(task, subagent_config, org_id, available_tools):
            return {
                "task": task,
                "subagent_kind": subagent_config.get("subagent_kind", "USER_SUB"),
                "status": "succeeded",
                "result_text": f"[Mock] {task}",
                "error_message": "",
                "tool_calls_made": 0,
            }

        graph = create_supervisor_graph(subagent_executor=mock_subagent_executor)

        initial_state = {
            "user_input": "搜索Python文档",
            "org_id": "org_1",
            "agent_id": "agent_1",
            "workspace_id": "ws_1",
            "available_subagents": [{"agent_id": "rag_1", "kind": "SYSTEM_RAG", "name": "RAG", "description": "知识检索"}],
            "available_tools": [],
            "iteration": 0,
            "max_iterations": 3,
        }

        result = await graph.ainvoke(initial_state)
        assert result.get("final_response") is not None
        assert len(result.get("subtask_results", [])) >= 1


# ─── ReAct Agent 测试 ───


class TestReActAgent:
    """测试 LangGraph ReAct Agent。"""

    @pytest.mark.asyncio
    async def test_execute_no_tools(self):
        from packages.runtime.langgraph_executor import LangGraphReActExecutor

        class SimpleMockChatModel:
            _llm_type = "simple_mock"
            bound_tools = []

            async def ainvoke(self, messages, **kwargs):
                from langchain_core.messages import AIMessage
                return AIMessage(content="Mock response")

            def bind_tools(self, tools):
                return self

        executor = LangGraphReActExecutor(chat_model=SimpleMockChatModel())
        result = await executor.execute(task="Hello", subagent_kind="USER_SUB")
        assert result["status"] == "succeeded"
        assert "Mock response" in result["result_text"]

    @pytest.mark.asyncio
    async def test_react_with_tools(self):
        """端到端：ReAct Agent 调用工具然后生成最终回答。"""
        from langchain_core.language_models.chat_models import BaseChatModel
        from langchain_core.messages import AIMessage
        from langchain_core.outputs import ChatGeneration, ChatResult
        from packages.runtime.langgraph_executor import LangGraphReActExecutor
        from packages.runtime.tools.rag_tool import RAGSearchTool

        class ReactMockChatModel(BaseChatModel):
            _call_count: int = 0
            bound_tools: list = []

            class Config:
                arbitrary_types_allowed = True

            @property
            def _llm_type(self) -> str:
                return "react_mock"

            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                self._call_count += 1
                if self._call_count == 1:
                    msg = AIMessage(
                        content="",
                        tool_calls=[{"name": "knowledge_search", "args": {"query": "Python"}, "id": "call_1", "type": "tool_call"}],
                    )
                else:
                    msg = AIMessage(content="Python tutorial results found.")
                return ChatResult(generations=[ChatGeneration(message=msg)])

            def bind_tools(self, tools, **kwargs):
                self.bound_tools = tools
                return self

        async def mock_rag(query, collection, top_k, org_id, agent_id):
            return [{"content": "Python basics", "score": 0.95}]

        rag_tool = RAGSearchTool(org_id="org_1", agent_id="agent_1", rag_executor=mock_rag)
        executor = LangGraphReActExecutor(chat_model=ReactMockChatModel(), max_iterations=5)

        result = await executor.execute(task="Search Python", subagent_kind="SYSTEM_RAG", tools=[rag_tool])
        assert result["status"] == "succeeded"
        assert result["tool_calls_made"] >= 1

    @pytest.mark.asyncio
    async def test_execute_failure(self):
        from packages.runtime.langgraph_executor import LangGraphReActExecutor

        class FailingChatModel:
            _llm_type = "failing"
            bound_tools = []

            async def ainvoke(self, messages, **kwargs):
                raise RuntimeError("LLM unavailable")

            def bind_tools(self, tools):
                return self

        executor = LangGraphReActExecutor(chat_model=FailingChatModel())
        result = await executor.execute(task="test", subagent_kind="USER_SUB")
        assert result["status"] == "failed"
        assert "LLM unavailable" in result["error_message"]
