"""A2A (Agent-to-Agent) 协议路由 - 提供外部 Agent Card 发现和 Task 交互端点。

v0.3 升级：
- Agent Card 从数据库读取
- A2A Task 对接 Supervisor/ExecutionEngine 真正执行
- 支持 A2A Task 状态查询和取消
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from packages.a2a.agent_card import build_agent_card


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


@router.get("/agents/{agent_id}/card")
async def get_agent_card(agent_id: str, db: AsyncSession = Depends()):
    """获取 Agent Card - A2A 协议发现端点。

    从数据库读取 Agent 信息，生成符合 A2A 规范的 Agent Card。
    """
    try:
        from apps.api.app.services.db.agent_db import agent_db
        from apps.api.app.services.db.runtime_db import skill_db

        agent = await agent_db.get(db, agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        # 获取 Agent 的 Skill 列表
        agent_obj = agent
        skills = []
        try:
            skill_list = await skill_db.list_by_agent(db, agent_id, agent_obj.org_id)
            skills = [
                {"id": str(s.skill_id), "name": s.name, "description": s.description}
                for s in skill_list
            ] if skill_list else []
        except Exception:
            pass

        # 构建 Agent Card
        base_url = "http://localhost:8000"  # TODO: 从配置读取
        card = build_agent_card(
            agent_id=agent_id,
            name=agent_obj.name,
            description=agent_obj.description,
            base_url=base_url,
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
    db: AsyncSession = Depends(),
):
    """创建 A2A Task - 外部系统向 Agent 发送任务。

    任务通过 AgentRuntime 执行：
    - Supervisor Agent: plan → execute → reflect → aggregate
    - 普通 Agent: 直接 LLM 调用
    """
    import uuid

    try:
        from apps.api.app.services.db.agent_db import agent_db
        from apps.api.app.services.db.session_db import session_db, session_message_db

        # 验证 Agent 存在
        agent = await agent_db.get(db, agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        task_id = str(uuid.uuid4())

        # 创建或复用 Session
        session_id = request.session_id
        if not session_id:
            session = await session_db.create(db, obj_in={
                "org_id": agent.org_id,
                "agent_id": agent_id,
                "title": f"A2A Task: {request.message[:50]}",
                "meta_info": {"a2a_task_id": task_id},
            })
            session_id = str(session.session_id)

        # 保存用户消息
        await session_message_db.create(db, obj_in={
            "session_id": session_id,
            "role": "user",
            "content": request.message,
            "meta_info": {"a2a_task_id": task_id, "priority": request.priority},
        })

        if request.async_exec:
            # 异步执行：通过 Celery 任务
            from apps.worker.app.tasks.subagent import supervisor_run_cycle

            # 获取 Agent kind
            agent_kind = getattr(agent, "kind", "USER_SUB")
            if agent_kind == "SUPERVISOR":
                task_result = supervisor_run_cycle.delay(
                    supervisor_agent_id=agent_id,
                    org_id=agent.org_id,
                    user_input=request.message,
                )
            else:
                # 普通 Agent：直接作为 SubAgent 执行
                from apps.worker.app.tasks.subagent import execute_subagent_task
                task_result = execute_subagent_task.delay(
                    run_data={
                        "run_id": task_id,
                        "task": request.message,
                        "assigned_subagent_id": agent_id,
                        "child_session_key": session_id,
                        "spawn_mode": "sync",
                    },
                    org_id=agent.org_id,
                )

            return A2ATaskResponse(
                task_id=task_id,
                status="pending",
                result=None,
                agent_id=agent_id,
            )
        else:
            # 同步执行
            from packages.runtime.llm_caller import LLMCallerAdapter
            from packages.runtime.agent_runtime import AgentRuntime

            adapter = LLMCallerAdapter(
                provider=getattr(agent, "model_provider", "mock"),
                model=getattr(agent, "model_name", "mock-model"),
                org_id=agent.org_id,
            )

            runtime = AgentRuntime(
                agent_id=agent_id,
                org_id=agent.org_id,
                model_provider=getattr(agent, "model_provider", "mock"),
                model_name=getattr(agent, "model_name", "mock-model"),
                workspace_id=getattr(agent, "workspace_id", ""),
                llm_caller=adapter,
            )

            # 如果是 Supervisor，初始化
            agent_kind = getattr(agent, "kind", "USER_SUB")
            if agent_kind == "SUPERVISOR":
                runtime.init_supervisor(llm_caller=adapter)

            result = await runtime.chat(request.message, session_id=session_id)

            # 保存助手消息
            response_text = result.get("response", "")
            await session_message_db.create(db, obj_in={
                "session_id": session_id,
                "role": "assistant",
                "content": response_text,
                "meta_info": {
                    "a2a_task_id": task_id,
                    "intent": result.get("intent", ""),
                    "plan_id": result.get("plan_id", ""),
                },
            })

            return A2ATaskResponse(
                task_id=task_id,
                status="succeeded",
                result=response_text,
                agent_id=agent_id,
            )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"A2A Task 执行失败: {exc}")


@router.get("/agents/{agent_id}/tasks/{task_id}", response_model=A2ATaskResponse)
async def get_a2a_task(agent_id: str, task_id: str, db: AsyncSession = Depends()):
    """查询 A2A Task 状态。

    从 Session Message 中查找任务结果。
    """
    try:
        from apps.api.app.services.db.session_db import session_message_db

        # 通过 meta_info 中的 a2a_task_id 查找
        # MVP: 简化实现，通过 session 查找
        # 后续需要专门的 A2A Task 表
        raise HTTPException(status_code=404, detail="Task not found (A2A Task 表待实现)")

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"查询 A2A Task 失败: {exc}")


@router.post("/agents/{agent_id}/tasks/{task_id}/messages")
async def send_a2a_message(
    agent_id: str,
    task_id: str,
    request: A2AMessageRequest,
    db: AsyncSession = Depends(),
):
    """向 A2A Task 追加消息。

    对应 Supervisor 的 announce 语义。
    """
    try:
        from apps.api.app.services.db.session_db import session_message_db

        # 追加消息到 Session
        await session_message_db.create(db, obj_in={
            "session_id": task_id,  # 使用 task_id 作为 session_id
            "role": "user",
            "content": request.message,
            "meta_info": {"a2a_task_id": task_id, "type": "announce"},
        })

        return {"status": "announced", "task_id": task_id}

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"追加消息失败: {exc}")
