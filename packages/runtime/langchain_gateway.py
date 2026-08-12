"""LLMGateway → LangChain BaseChatModel 桥接层。

将项目自有的 LLMGateway 适配为 LangChain 的 BaseChatModel，
使得 LangGraph 和 LangChain Agent 可以直接使用项目的 LLM Gateway。

关键特性：
- 消息格式转换：LangChain BaseMessage → Gateway prompt 文本
- tool_calls 解析：从 OpenAI 格式响应中提取 tool_calls
- bind_tools 支持：将 LangChain Tool 的 schema 传给 LLM
"""

import hashlib
import json
import logging
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    ChatMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult

logger = logging.getLogger(__name__)


def _messages_to_prompt(messages: list[BaseMessage]) -> str:
    """将 LangChain 消息列表转换为文本 prompt（用于不支持消息列表的 Gateway）。"""
    parts: list[str] = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            parts.append(f"[System]\n{msg.content}")
        elif isinstance(msg, HumanMessage):
            parts.append(f"[User]\n{msg.content}")
        elif isinstance(msg, AIMessage):
            if msg.content:
                parts.append(f"[Assistant]\n{msg.content}")
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    parts.append(f"[Assistant-ToolCall] {tc['name']}({json.dumps(tc.get('args', {}), ensure_ascii=False)})")
        elif isinstance(msg, ToolMessage):
            parts.append(f"[Tool-{msg.name}] {msg.content}")
        elif isinstance(msg, ChatMessage):
            parts.append(f"[{msg.role}]\n{msg.content}")
        else:
            parts.append(str(msg.content))
    return "\n\n".join(parts)


class GatewayChatModel(BaseChatModel):
    """将 LLMGateway 适配为 LangChain BaseChatModel。

    使用方式：
        gateway = LLMGateway(providers={...})
        chat_model = GatewayChatModel.from_gateway(gateway, provider="openai", model="gpt-4o")
        # 然后可以传给 LangGraph / LangChain Agent
    """

    gateway: Any = None  # LLMGateway 实例
    provider: str = ""
    model: str = ""
    org_id: str = ""
    actor_user_id: str = ""
    bound_tools: list[dict[str, Any]] = []
    native_tool_calls: bool = True

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_gateway(
        cls,
        gateway: Any,
        provider: str = "",
        model: str = "",
        org_id: str = "",
        actor_user_id: str = "",
    ) -> "GatewayChatModel":
        """从 LLMGateway 实例创建 GatewayChatModel。"""
        return cls(
            gateway=gateway,
            provider=provider,
            model=model,
            org_id=org_id,
            actor_user_id=actor_user_id,
        )

    @property
    def _llm_type(self) -> str:
        return f"gateway-{self.provider}"

    def bind_tools(self, tools: list, **kwargs) -> "GatewayChatModel":
        """将工具绑定到模型，返回新实例。"""
        tool_schemas = []
        for tool in tools:
            schema: dict[str, Any] = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                },
            }
            if hasattr(tool, "args_schema") and tool.args_schema:
                schema["function"]["parameters"] = tool.args_schema.schema()
            else:
                schema["function"]["parameters"] = {"type": "object", "properties": {}}
            tool_schemas.append(schema)

        return GatewayChatModel(
            gateway=self.gateway,
            provider=self.provider,
            model=self.model,
            org_id=self.org_id,
            actor_user_id=self.actor_user_id,
            bound_tools=tool_schemas,
            native_tool_calls=self.native_tool_calls,
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """同步生成（内部调用异步）。"""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # 如果已在异步上下文中，用 run_until_complete 会报错
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs))
                return future.result()
        else:
            return asyncio.run(self._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs))

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        """异步生成。"""
        if not self.gateway:
            raise ValueError("GatewayChatModel 未配置真实 Gateway")
        if not self.provider or not self.model:
            raise ValueError("GatewayChatModel 未配置真实模型供应商和模型")

        from apps.api.app.gateway.llm import LLMCallRequest

        prompt_text = _messages_to_prompt(messages)

        # Reasonix 风格前缀缓存观测：系统消息构成稳定前缀，对其取 hash 后
        # 计量侧可以按 prefix_hash 聚合缓存命中表现（与 LLMCallerAdapter 一致）。
        system_prefix = "\n\n".join(
            str(message.content) for message in messages if isinstance(message, SystemMessage)
        )

        request = LLMCallRequest(
            provider=self.provider,
            model=self.model,
            prompt=prompt_text,
            prefix_hash=(
                hashlib.sha256(system_prefix.encode("utf-8")).hexdigest() if system_prefix else ""
            ),
            parameters={
                "temperature": kwargs.get("temperature", 0.3),
                "max_tokens": kwargs.get("max_tokens", 2048),
                "tools": self.bound_tools if self.bound_tools else None,
            },
            metadata={
                "source": "langchain_gateway_chat_model",
                "org_id": self.org_id,
                "actor_user_id": self.actor_user_id,
            },
        )

        try:
            response = await self.gateway.generate(request)
        except Exception as exc:
            logger.error(f"Gateway 调用失败: {exc}")
            raise

        # 尝试解析 tool_calls
        tool_calls = self._extract_tool_calls(response.raw_response if hasattr(response, "raw_response") else {})

        ai_message = AIMessage(
            content=response.text,
            tool_calls=tool_calls if tool_calls else [],
        )

        return ChatResult(generations=[ChatGeneration(message=ai_message)])

    def _extract_tool_calls(self, raw_response: Any) -> list[dict[str, Any]]:
        """从原始响应中提取 tool_calls（OpenAI 格式）。"""
        if not raw_response or not self.bound_tools:
            return []

        if isinstance(raw_response, dict):
            choices = raw_response.get("choices", [])
            if choices:
                message = choices[0].get("message", {})
                tool_calls = message.get("tool_calls")
                if tool_calls:
                    return [
                        {
                            "name": tc.get("function", {}).get("name", ""),
                            "args": json.loads(tc.get("function", {}).get("arguments", "{}")),
                            "id": tc.get("id", ""),
                            "type": "tool_call",
                        }
                        for tc in tool_calls
                    ]
        return []
