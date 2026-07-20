"""LLM 调用适配器 - 将 packages/runtime 的 LLM 调用需求桥接到 Gateway。

Supervisor、Skill Evolver 等运行时组件通过此适配器调用 LLM Gateway，
无需直接依赖 Gateway 的具体实现。
"""

import hashlib
from typing import Any, Mapping, Protocol

from apps.api.app.gateway.llm import LLMCallRequest, LLMGateway, llm_gateway


class LLMCallerAdapter:
    """将 LLMGateway 适配为 runtime 层的 LLMCaller 协议。

    使用方式：
        adapter = LLMCallerAdapter(gateway=llm_gateway, provider="openai", model="gpt-4o")
        supervisor = SupervisorAgent(agent_id=..., llm_caller=adapter)
    """

    def __init__(
        self,
        gateway: LLMGateway | None = None,
        provider: str = "",
        model: str = "",
        org_id: str = "",
        actor_user_id: str = "",
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        self.gateway = gateway or llm_gateway
        if not provider or not model:
            raise ValueError("LLMCallerAdapter 需要真实模型供应商和模型名称")
        self.provider = provider
        self.model = model
        self.org_id = org_id
        self.actor_user_id = actor_user_id
        self.metadata = dict(metadata or {})

    async def call(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        """调用 LLM Gateway，返回响应文本。"""
        # 如果有 system_prompt，拼接到 prompt 前面
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"[System]\n{system_prompt}\n\n[User]\n{prompt}"

        request = LLMCallRequest(
            provider=self.provider,
            model=self.model,
            prompt=full_prompt,
            # The system prompt is sent first and is stable for a given Agent,
            # so it is the cacheable prefix for this legacy runtime path too.
            prefix_hash=(
                hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()
                if system_prompt
                else None
            ),
            parameters={
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            metadata={
                "source": "runtime_llm_caller",
                "org_id": self.org_id,
                "actor_user_id": self.actor_user_id,
                **self.metadata,
            },
        )
        response = await self.gateway.generate(request)
        return response.text


class SkillEvolverLLMCaller:
    """Skill Evolver 专用的 LLM 调用器。

    与通用 LLMCallerAdapter 不同，此调用器：
    1. 使用专门的 Skill Evolver system prompt
    2. 支持结构化输出（SKILL.md 格式）
    3. 记录进化历史用于追踪
    """

    EVOLVER_SYSTEM_PROMPT = """你是一个 Skill Evolver Agent。你的职责是根据 Agent 的运行历史和反馈，自动创建、更新和优化 SKILL.md 技能文件。

SKILL.md 格式规范：
---
name: 技能名称
description: 技能描述
trigger_conditions:
  - 触发条件1
  - 触发条件2
version: 1.0.0
author: skill_evolver
created_at: 创建时间
updated_at: 更新时间
---

# 技能名称

## 步骤
1. 步骤1
2. 步骤2

## 示例
- 示例1

## 注意事项
- 注意事项1

你必须以 JSON 格式输出，格式如下：
{
  "action": "create|update|deprecate",
  "skill_name": "技能名称",
  "skill_content": "完整的 SKILL.md 内容",
  "reasoning": "进化推理过程",
  "confidence": 0.0-1.0
}"""

    def __init__(
        self,
        gateway: LLMGateway | None = None,
        provider: str = "",
        model: str = "",
        org_id: str = "",
    ) -> None:
        self.gateway = gateway or llm_gateway
        if not provider or not model:
            raise ValueError("SkillEvolverLLMCaller 需要真实模型供应商和模型名称")
        self.provider = provider
        self.model = model
        self.org_id = org_id
        self._evolution_history: list[dict[str, Any]] = []

    async def call(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        """调用 LLM 进行 Skill 进化。"""
        full_prompt = prompt
        if not system_prompt:
            system_prompt = self.EVOLVER_SYSTEM_PROMPT

        if system_prompt:
            full_prompt = f"[System]\n{system_prompt}\n\n[User]\n{prompt}"

        request = LLMCallRequest(
            provider=self.provider,
            model=self.model,
            prompt=full_prompt,
            parameters={
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            metadata={
                "source": "skill_evolver",
                "org_id": self.org_id,
            },
        )
        response = await self.gateway.generate(request)

        # 记录进化历史
        self._evolution_history.append({
            "prompt_preview": prompt[:200],
            "response_preview": response.text[:200],
            "provider": response.provider,
            "model": response.model,
            "usage": response.usage,
        })

        return response.text

    def get_evolution_history(self) -> list[dict[str, Any]]:
        """返回进化历史。"""
        return list(self._evolution_history)
