"""知识库列举工具 → LangChain BaseTool 包装器。

安全读路径：只返回组织内知识库的元数据（ID/名称/描述），
帮助 Supervisor 在检索前判断该往哪个知识库搜索，避免盲目全量检索。
"""

import json
from typing import Any

from langchain_core.tools import BaseTool


class KnowledgeListTool(BaseTool):
    """List the knowledge bases the current Agent's organization can search."""

    name: str = "knowledge_list"
    description: str = (
        "List knowledge bases available to this Agent's organization (id, name, "
        "description only). Use it to decide where to search before calling "
        "knowledge_search; returns metadata, never document content."
    )
    org_id: str = ""
    agent_id: str = ""
    knowledge_list_accessor: Any = None  # 异步知识库列举函数

    class Config:
        arbitrary_types_allowed = True

    def _run(self, **kwargs: Any) -> str:
        import asyncio

        return asyncio.run(self._arun(**kwargs))

    async def _arun(self, **kwargs: Any) -> str:
        if not self.knowledge_list_accessor:
            return json.dumps({"error": "Knowledge list accessor 未配置"}, ensure_ascii=False)
        try:
            result = self.knowledge_list_accessor(org_id=self.org_id)
            if asyncio.iscoroutine(result):
                result = await result
            return json.dumps(result, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
