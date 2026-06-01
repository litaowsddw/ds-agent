"""WebSocket / SSE 实时事件推送端点。

提供：
- WebSocket 长连接：/ws/events
- SSE 降级方案：/sse/events

用于实时推送 Workflow 运行状态、Session 消息、系统通知等。
"""

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sse_starlette.sse import EventSourceResponse

router = APIRouter()


class ConnectionManager:
    """WebSocket 连接管理器。"""

    def __init__(self) -> None:
        # active_connections 保存所有活跃的 WebSocket 连接。
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """接受新的 WebSocket 连接。"""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """断开 WebSocket 连接。"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, event: str, data: Any) -> None:
        """向所有连接广播事件。"""
        message = json.dumps({"event": event, "data": data}, ensure_ascii=False)
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

    async def send_to(self, websocket: WebSocket, event: str, data: Any) -> None:
        """向单个连接发送事件。"""
        message = json.dumps({"event": event, "data": data}, ensure_ascii=False)
        try:
            await websocket.send_text(message)
        except Exception:
            self.disconnect(websocket)


# 全局连接管理器
manager = ConnectionManager()


@router.websocket("/events")
async def websocket_events(websocket: WebSocket) -> None:
    """WebSocket 事件推送端点。

    客户端连接后可接收：
    - workflow_run: Workflow 运行状态变更
    - session_message: Session 新消息
    - system_notification: 系统通知
    """
    await manager.connect(websocket)
    try:
        while True:
            # 接收客户端消息（心跳/订阅等）
            data = await websocket.receive_text()
            try:
                parsed = json.loads(data)
                # 处理客户端发来的订阅请求等
                event_type = parsed.get("event")
                if event_type == "ping":
                    await manager.send_to(websocket, "pong", {"ts": __import__("time").time()})
            except (json.JSONDecodeError, KeyError):
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)


async def _sse_event_generator():
    """SSE 事件生成器（降级方案）。"""
    # 每隔 30 秒发送心跳
    while True:
        yield {"event": "ping", "data": json.dumps({"ts": __import__("time").time()})}
        await asyncio.sleep(30)


@router.get("/events")
async def sse_events() -> EventSourceResponse:
    """SSE 事件推送端点（降级方案）。

    当 WebSocket 不可用时，客户端可使用 SSE 接收事件。
    """
    return EventSourceResponse(_sse_event_generator())


async def emit_event(event: str, data: Any) -> None:
    """全局事件推送函数。

    供其他模块调用，广播实时事件到所有已连接的客户端。
    """
    await manager.broadcast(event, data)
