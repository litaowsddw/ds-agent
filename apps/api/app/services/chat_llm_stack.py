"""Chat 路径共享的 LLM 调用栈构建。

/chat/、/chat/stream 与 A2A Task 同步执行都需要同一套 Gateway + 文本调用适配器
+ LangChain ChatModel 组合。集中在这里，避免三条路径各自复制 provider 解密、
metering recorder 和模型身份配置而漂移。
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_api_key
from app.services.metering import SessionUsageRecorder, UsageContext


async def build_chat_llm_stack(
    db: AsyncSession,
    *,
    agent: Any,
    actor_user_id: str,
    source: str,
    session_id: str,
) -> tuple[Any, Any, Any]:
    """构建 (LLMGateway, LLMCallerAdapter, GatewayChatModel)。

    - gateway：按 Agent 配置的 provider 构造，带计量 recorder
    - adapter：runtime 文本调用协议（legacy caller 接口）
    - chat_model：LangGraph Supervisor / ReAct 执行器的 LangChain 模型
    """
    from fastapi import HTTPException

    from apps.api.app.gateway.llm import LLMGateway, OpenAICompatibleProvider, llm_gateway
    from apps.api.app.services.db.runtime_db import model_provider_db
    from packages.runtime.langchain_gateway import GatewayChatModel
    from packages.runtime.llm_caller import LLMCallerAdapter

    org_id = str(agent.org_id)
    model_provider = agent.model_provider or ""
    model_name = agent.model_name or ""
    if not model_provider or not model_name:
        raise HTTPException(status_code=400, detail="Agent has no model provider or model configured")

    provider_config = await model_provider_db.get_by_key(db, org_id, model_provider)
    if provider_config is None or not provider_config.is_enabled:
        raise HTTPException(status_code=400, detail=f"Model provider not configured: {model_provider}")

    gateway = LLMGateway(
        providers={
            model_provider: OpenAICompatibleProvider(
                base_url=provider_config.base_url,
                api_key=(
                    decrypt_api_key(provider_config.api_key_encrypted)
                    if provider_config.api_key_encrypted
                    else ""
                ),
                provider_key=model_provider,
            )
        },
        limiter=llm_gateway.limiter,
        usage_recorder=SessionUsageRecorder(db),
    )
    adapter = LLMCallerAdapter(
        gateway=gateway,
        provider=model_provider,
        model=model_name,
        org_id=org_id,
        actor_user_id=actor_user_id,
        metadata=UsageContext(
            org_id=org_id,
            actor_user_id=actor_user_id,
            source=source,
            api_name="chat.completions",
            agent_id=str(agent.agent_id),
            session_id=str(session_id),
        ).as_metadata(),
    )
    chat_model = GatewayChatModel.from_gateway(
        gateway=gateway,
        provider=model_provider,
        model=model_name,
        org_id=org_id,
        actor_user_id=actor_user_id,
    )
    return gateway, adapter, chat_model
