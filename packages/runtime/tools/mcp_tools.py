"""MCP 工具 → LangChain BaseTool 包装器。"""

import json
import inspect
from typing import Any

from langchain_core.tools import BaseTool


class MCPTool(BaseTool):
    """将 MCP 工具包装为 LangChain BaseTool。

    支持动态发现 MCP 工具、授权校验和异步调用。
    """

    name: str = "mcp_tool"
    description: str = "MCP 工具调用"
    org_id: str = ""
    agent_id: str = ""
    mcp_accessor: Any = None  # ToolAccessor Protocol

    class Config:
        arbitrary_types_allowed = True

    def _run(self, **kwargs: Any) -> str:
        """同步执行（内部调用异步）。"""
        import asyncio
        return asyncio.run(self._arun(**kwargs))

    async def _arun(self, **kwargs: Any) -> str:
        """异步执行 MCP 工具调用。"""
        if not self.mcp_accessor:
            return json.dumps({"error": "MCP accessor 未配置"}, ensure_ascii=False)

        try:
            # The injected accessor is responsible for Agent-policy filtering.
            # Supporting both synchronous registries and async DB-backed
            # accessors keeps this wrapper usable in either runtime.
            tools = self.mcp_accessor.get_available_tools(self.org_id, self.agent_id)
            if inspect.isawaitable(tools):
                tools = await tools
            tool_info = next((t for t in tools if t.get("name") == self.name), None)

            if not tool_info:
                return json.dumps({"error": f"未找到 MCP 工具: {self.name}"}, ensure_ascii=False)

            # 执行工具调用
            result = self.mcp_accessor.call_tool(
                org_id=self.org_id,
                agent_id=self.agent_id,
                tool_name=self.name,
                arguments=kwargs,
            )
            if inspect.isawaitable(result):
                result = await result
            return json.dumps(result, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
