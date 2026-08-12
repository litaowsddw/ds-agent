"""Agent Runtime 包。

该包承载 OpenClaw 风格的运行时抽象，包括上下文、Skill、MCP、内存和 Prompt 编译。

v0.4 — LangGraph + LangChain 单一执行路径：
- Supervisor 使用 LangGraph StateGraph（plan → delegate → reflect → respond）
- SubAgent 使用 LangGraph ReAct Agent（支持真正的工具调用循环）
- LLM 调用通过 GatewayChatModel 桥接到 LLMGateway
- 工具（MCP/RAG/Skill/Memory）包装为 LangChain BaseTool

主要导出：
- AgentRuntime: 运行时门面
- GatewayChatModel: LLMGateway → LangChain BaseChatModel 桥接
- LangGraphReActExecutor: ReAct 执行引擎
- create_supervisor_graph: Supervisor StateGraph 工厂
"""
