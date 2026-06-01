"""Chat API 路由 - Supervisor Agent 对话入口。

提供与 Agent 的对话接口，支持：
- 同步对话
- 流式响应（SSE）
- 异步对话（Celery）
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class ChatRequest(BaseModel):
    """对话请求。"""
    # agent_id 是对话的 Agent ID
    agent_id: str
    # org_id 是组织 ID
    org_id: str
    # message 是用户消息
    message: str
    # session_id 是会话 ID（可选，用于多轮对话）
    session_id: str | None = None
    # 是否流式响应
    stream: bool = False
    # 是否异步执行
    async_exec: bool = False


class ChatResponse(BaseModel):
    """对话响应。"""
    # response 是 Agent 回复
    response: str
    # agent_id 是 Agent ID
    agent_id: str
    # session_id 是会话 ID
    session_id: str
    # mode 是执行模式
    mode: str  # "supervisor" | "direct" | "mock"
    # intent 是意图识别结果（Supervisor 模式）
    intent: str = ""
    # subtask_count 是子任务数量（Supervisor 模式）
    subtask_count: int = 0
    # succeeded_count 是成功子任务数
    succeeded_count: int = 0
    # plan_id 是任务计划 ID
    plan_id: str = ""


@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(),
):
    """与 Agent 对话。

    Supervisor Agent 会执行完整的 plan → execute → reflect 循环。
    普通 Agent 直接调用 LLM。
    """
    try:
        from apps.api.app.services.db.agent_db import agent_db
        from apps.api.app.services.db.session_db import session_db, session_message_db
        from packages.runtime.agent_runtime import AgentRuntime, AgentKind
        from packages.runtime.llm_caller import LLMCallerAdapter

        # 1. 获取 Agent 配置
        agent = await agent_db.get(db, request.agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        # 2. 创建或复用 Session
        session_id = request.session_id
        if not session_id:
            session = await session_db.create(db, obj_in={
                "org_id": request.org_id,
                "agent_id": request.agent_id,
                "title": f"Chat: {request.message[:50]}",
            })
            session_id = str(session.session_id)

        # 3. 保存用户消息
        await session_message_db.create(db, obj_in={
            "session_id": session_id,
            "role": "user",
            "content": request.message,
        })

        # 4. 构建 LLM 调用器
        adapter = LLMCallerAdapter(
            provider=getattr(agent, "model_provider", "mock"),
            model=getattr(agent, "model_name", "mock-model"),
            org_id=request.org_id,
        )

        # 5. 构建 AgentRuntime
        runtime = AgentRuntime(
            agent_id=request.agent_id,
            org_id=request.org_id,
            model_provider=getattr(agent, "model_provider", "mock"),
            model_name=getattr(agent, "model_name", "mock-model"),
            workspace_id=getattr(agent, "workspace_id", ""),
            llm_caller=adapter,
        )

        # 6. 如果是 Supervisor，初始化
        agent_kind_str = getattr(agent, "kind", "USER_SUB")
        if agent_kind_str == "SUPERVISOR":
            runtime.init_supervisor(llm_caller=adapter)

        # 7. 异步执行模式
        if request.async_exec:
            from apps.worker.app.tasks.subagent import supervisor_run_cycle
            task = supervisor_run_cycle.delay(
                supervisor_agent_id=request.agent_id,
                org_id=request.org_id,
                user_input=request.message,
            )
            return ChatResponse(
                response="任务已提交，正在异步执行...",
                agent_id=request.agent_id,
                session_id=session_id,
                mode="async",
            )

        # 8. 同步执行
        result = await runtime.chat(request.message, session_id=session_id)

        # 9. 保存助手消息（如果还没保存）
        response_text = result.get("response", "")
        if response_text:
            # 检查是否已经保存（Supervisor 可能已保存）
            try:
                await session_message_db.create(db, obj_in={
                    "session_id": session_id,
                    "role": "assistant",
                    "content": response_text,
                    "meta_info": {
                        "intent": result.get("intent", ""),
                        "plan_id": result.get("plan_id", ""),
                    },
                })
            except Exception:
                pass

        return ChatResponse(
            response=response_text,
            agent_id=request.agent_id,
            session_id=session_id,
            mode=result.get("mode", "supervisor" if agent_kind_str == "SUPERVISOR" else "direct"),
            intent=result.get("intent", ""),
            subtask_count=result.get("subtask_count", 0),
            succeeded_count=result.get("succeeded_count", 0),
            plan_id=result.get("plan_id", ""),
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"对话失败: {exc}")


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(),
):
    """获取会话消息历史。"""
    try:
        from apps.api.app.services.db.session_db import session_message_db

        messages = await session_message_db.list_by_session(db, session_id, limit=limit)

        return {
            "session_id": session_id,
            "messages": [
                {
                    "message_id": str(m.message_id),
                    "role": m.role,
                    "content": m.content,
                    "sequence": m.sequence,
                    "meta_info": m.meta_info,
                    "created_at": str(m.created_at) if m.created_at else "",
                }
                for m in messages
            ] if messages else [],
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取消息失败: {exc}")
