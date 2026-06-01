"""记忆召回工具 → LangChain BaseTool 包装器。"""

import json
from typing import Any

from langchain_core.tools import BaseTool


class MemoryRecallTool(BaseTool):
    """将记忆召回包装为 LangChain BaseTool。"""

    name: str = "memory_recall"
    description: str = "从记忆库中召回与查询相关的历史对话和记忆。"
    org_id: str = ""
    agent_id: str = ""
    memory_accessor: Any = None  # 异步 Memory 访问函数

    class Config:
        arbitrary_types_allowed = True

    def _run(self, query: str, top_k: int = 5, **kwargs: Any) -> str:
        """同步执行。"""
        import asyncio
        return asyncio.run(self._arun(query=query, top_k=top_k, **kwargs))

    async def _arun(self, query: str, top_k: int = 5, **kwargs: Any) -> str:
        """异步执行记忆召回。"""
        if not self.memory_accessor:
            return json.dumps({"error": "Memory accessor 未配置"}, ensure_ascii=False)

        try:
            results = await self.memory_accessor(
                query=query,
                org_id=self.org_id,
                agent_id=self.agent_id,
                top_k=top_k,
            )
            return json.dumps(results, ensure_ascii=False) if isinstance(results, (dict, list)) else str(results)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
