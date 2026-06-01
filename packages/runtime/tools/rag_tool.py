"""RAG 检索工具 → LangChain BaseTool 包装器。"""

import json
from typing import Any

from langchain_core.tools import BaseTool


class RAGSearchTool(BaseTool):
    """将 RAG 知识检索包装为 LangChain BaseTool。"""

    name: str = "knowledge_search"
    description: str = "从知识库中检索相关文档和知识片段。输入查询关键词和可选的集合名称。"
    org_id: str = ""
    agent_id: str = ""
    rag_executor: Any = None  # 异步 RAG 执行函数

    class Config:
        arbitrary_types_allowed = True

    def _run(self, query: str, collection: str = "default", top_k: int = 5, **kwargs: Any) -> str:
        """同步执行。"""
        import asyncio
        return asyncio.run(self._arun(query=query, collection=collection, top_k=top_k, **kwargs))

    async def _arun(self, query: str, collection: str = "default", top_k: int = 5, **kwargs: Any) -> str:
        """异步执行 RAG 检索。"""
        if not self.rag_executor:
            return json.dumps({"error": "RAG executor 未配置"}, ensure_ascii=False)

        try:
            results = await self.rag_executor(
                query=query,
                collection=collection,
                top_k=top_k,
                org_id=self.org_id,
                agent_id=self.agent_id,
            )
            return json.dumps(results, ensure_ascii=False) if isinstance(results, (dict, list)) else str(results)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
