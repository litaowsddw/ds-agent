"""Skill 创建工具 → LangChain BaseTool 包装器。"""

import json
from typing import Any

from langchain_core.tools import BaseTool


class SkillCreatorTool(BaseTool):
    """将 Skill 创建包装为 LangChain BaseTool。"""

    name: str = "skill_create"
    description: str = "创建或更新一个技能（Skill）。需要提供技能名称、描述和指令步骤。"
    org_id: str = ""
    agent_id: str = ""
    skill_accessor: Any = None  # 异步 Skill 访问函数

    class Config:
        arbitrary_types_allowed = True

    def _run(self, name: str, description: str, instructions: str = "", **kwargs: Any) -> str:
        """同步执行。"""
        import asyncio
        return asyncio.run(self._arun(name=name, description=description, instructions=instructions, **kwargs))

    async def _arun(self, name: str, description: str, instructions: str = "", **kwargs: Any) -> str:
        """异步执行 Skill 创建。"""
        if not self.skill_accessor:
            return json.dumps({"error": "Skill accessor 未配置"}, ensure_ascii=False)

        try:
            result = await self.skill_accessor(
                name=name,
                description=description,
                instructions=instructions,
                org_id=self.org_id,
                agent_id=self.agent_id,
            )
            return json.dumps(result, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
