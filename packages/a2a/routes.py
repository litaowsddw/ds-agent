"""A2A (Agent-to-Agent) 协议路由 - 提供外部 Agent Card 发现和 Task 交互端点。

v0.4 修复：
- 数据库会话走标准 get_db_session 依赖注入（此前 Depends() 为空，端点必崩）
- Agent Card 从数据库读取
- 同步 Task 通过 AgentRuntime（LangGraph Supervisor / 直接 LLM）真实执行
- 异步 Task 在计量归属就绪前明确返回 501，不再引用未注册的 Celery 任务
"""

import logging
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.domain.identity import new_id
from packages.a2a.agent_card import build_agent_card

logger = logging.getLogger(__name__)

router = APIRouter()


class A2ATaskRequest(BaseModel):
    """A2A Task 创建请求。"""
    # 消息内容
    message: str
    # 会话 ID（可选，用于多轮对话）
    session_id: str | None = None
    # 优先级
    priority: str = "normal"
    # 是否异步执行
    async_exec: bool = False


class A2ATaskResponse(BaseModel):
    """A2A Task 响应。"""
    task_id: str
    status: str
    result: str | None = None
    agent_id: str = ""


class A2AMessageRequest(BaseModel):
    """A2A 追加消息请求。"""
    message: str


def _public_base_url() -> str:
    """Agent Card 对外暴露的 API 地址，随部署环境配置。"""
    return os.getenv("AGENTFLOW_PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")


@router.get("/agents/{agent_id}/card")
async def get_agent_card(agent_id: str, db: AsyncSession = Depends(get_db_session)):
    """获取 Agent Card - A2A 协议发现端点。

    从数据库读取 Agent 信息，生成符合 A2A 规范的 Agent Card。
    """
    try:
        from apps.api.app.services.db.agent_db import agent_db
        from apps.api.app.services.db.runtime_db import skill_db

        try:
            agent = await agent_db.get_agent_required(db, agent_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Agent not found")

        # 获取 Agent 的 Skill 列表
        skills = []
        try:
            skill_list = await skill_db.list_agent_allowed_skills(db, agent_id, agent.org_id)
            skills = [
                {"id": str(s.skill_id), "name": s.name, "description": s.description}
                for s in skill_list
            ] if skill_list else []
        except Exception as exc:
            logger.warning("读取 Agent Skill 列表失败: %s", exc)

        # 构建 Agent Card
        card = build_agent_card(
            agent_id=agent_id,
            name=agent.name,
            description=agent.description,
            base_url=_public_base_url(),
            skills=skills,
        )
        return card.to_dict()

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取 Agent Card 失败: {exc}")


@router.post("/agents/{agent_id}/tasks", response_model=A2ATaskResponse)
async def create_a2a_task(
    agent_id: str,
    request: A2ATaskRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """创建 A2A Task - 外部系统向 Agent 发送任务。

    任务通过 AgentRuntime 执行：
    - Supervisor Agent: LangGraph plan → delegate → reflect → respond
    - 普通 Agent: 直接 LLM 调用
    """
    try:
        from apps.api.app.services.db.agent_db import agent_db
        from apps.api.app.services.db.session_db import session_db, session_message_db
        from app.services.chat_llm_stack import build_chat_llm_stack
        from packages.runtime.agent_runtime import AgentKind, AgentRuntime
        from packages.runtime.system_prompt import build_agent_system_prompt

        # 验证 Agent 存在
        try:
            agent = await agent_db.get_agent_required(db, agent_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Agent not found")

        if request.async_exec:
            raise HTTPException(
                status_code=501,
                detail="A2A 异步任务在计量归属就绪前暂不可用，请使用同步模式",
            )

        org_id = str(agent.org_id)
        task_id = str(uuid.uuid4())

        # 创建或复用 Session
        session_id = request.session_id or ""
        if session_id:
            try:
                existing_session = await session_db.get_session_required(db, session_id)
                if existing_session.org_id != org_id or existing_session.agent_id != agent_id:
                    raise ValueError("Session does not belong to this agent")
                session_id = str(existing_session.session_id)
            except ValueError:
                session_id = ""
        if not session_id:
            session = await session_db.create_session(
                db,
                session_id=new_id("ses"),
                org_id=org_id,
                agent_id=agent_id,
                user_id=str(agent.created_by),
            )
            session_id = str(session.session_id)

        # 保存用户消息
        await session_message_db.append_message(
            db,
            message_id=new_id("msg"),
            session_id=session_id,
            org_id=org_id,
            agent_id=agent_id,
            role="user",
            content=request.message,
            estimated_tokens=max(1, len(request.message) // 4),
            meta_info={"a2a_task_id": task_id, "priority": request.priority},
        )

        # 同步执行
        _, adapter, chat_model = await build_chat_llm_stack(
            db,
            agent=agent,
            actor_user_id=str(agent.created_by),
            source="a2a_task",
            session_id=session_id,
        )

        runtime = AgentRuntime(
            agent_id=agent_id,
            org_id=org_id,
            model_provider=str(getattr(agent, "model_provider", "") or ""),
            model_name=str(getattr(agent, "model_name", "") or ""),
            workspace_id=str(getattr(agent, "workspace_id", "") or ""),
            llm_caller=adapter,
            system_prompt=build_agent_system_prompt(
                agent_name=str(getattr(agent, "name", "") or "Agent"),
                agent_description=str(getattr(agent, "description", "") or ""),
                agent_instructions=str(getattr(agent, "system_prompt", "") or ""),
            ),
        )

        # 如果是 Supervisor，初始化
        agent_kind = str(getattr(agent, "kind", "USER_SUB") or "USER_SUB")
        if agent_kind in (AgentKind.SUPERVISOR.value, "SUPERVISOR"):
            runtime.init_supervisor(chat_model=chat_model, llm_caller=adapter)

        result = await runtime.chat(request.message, session_id=session_id)
        if result.get("error"):
            raise HTTPException(status_code=502, detail=str(result["error"]))

        # 保存助手消息
        response_text = str(result.get("response", ""))
        await session_message_db.append_message(
            db,
            message_id=new_id("msg"),
            session_id=session_id,
            org_id=org_id,
            agent_id=agent_id,
            role="assistant",
            content=response_text,
            estimated_tokens=max(1, len(response_text) // 4),
            meta_info={
                "a2a_task_id": task_id,
                "intent": str(result.get("intent", "")),
                "plan_id": str(result.get("plan_id", "")),
            },
        )
        await db.commit()

        return A2ATaskResponse(
            task_id=task_id,
            status="succeeded",
            result=response_text,
            agent_id=agent_id,
        )

    except HTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"A2A Task 执行失败: {exc}")


@router.get("/agents/{agent_id}/tasks/{task_id}", response_model=A2ATaskResponse)
async def get_a2a_task(agent_id: str, task_id: str, db: AsyncSession = Depends(get_db_session)):
    """查询 A2A Task 状态。

    从 Session Message 中查找任务结果。
    """
    # MVP: 简化实现，A2A Task 状态表待实现
    raise HTTPException(status_code=404, detail="Task not found (A2A Task 表待实现)")


@router.post("/agents/{agent_id}/tasks/{task_id}/messages")
async def send_a2a_message(
    agent_id: str,
    task_id: str,
    request: A2AMessageRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """向 A2A Task 追加消息。

    对应 Supervisor 的 announce 语义。
    """
    try:
        from apps.api.app.services.db.session_db import session_db, session_message_db

        # task_id 即会话 ID（创建 Task 时约定）
        session = await session_db.get_session_required(db, task_id)

        await session_message_db.append_message(
            db,
            message_id=new_id("msg"),
            session_id=str(session.session_id),
            org_id=str(session.org_id),
            agent_id=agent_id,
            role="user",
            content=request.message,
            estimated_tokens=max(1, len(request.message) // 4),
            meta_info={"a2a_task_id": task_id, "type": "announce"},
        )
        await db.commit()

        return {"status": "announced", "task_id": task_id}

    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"追加消息失败: {exc}")
