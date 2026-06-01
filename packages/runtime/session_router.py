"""Session 路由 - 管理 Supervisor 与 SubAgent 之间的会话键映射。

Session Key 层级设计（参考 OpenClaw）：
- 主会话：`agent:<supervisor_id>:main`
- 子会话：`agent:<supervisor_id>:subagent:<subagent_id>`

路由规则：
1. 用户消息进入 Supervisor 主会话
2. Supervisor spawn SubAgent 时，创建子会话
3. SubAgent 结果通过 settle 回写到主会话
 """

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SessionRoute:
    """会话路由条目。"""
    # session_key 是会话唯一键
    session_key: str
    # agent_id 是会话所属 Agent
    agent_id: str
    # parent_session_key 是父会话键（None 表示根会话）
    parent_session_key: str | None
    # depth 是嵌套深度（0=Supervisor 主会话，1=SubAgent 会话，2=Sub-SubAgent 会话...）
    depth: int
    # status 是会话状态
    status: str = "idle"  # idle/running/closed
    # metadata 是附加元数据
    metadata: dict[str, Any] = field(default_factory=dict)


class SessionRouter:
    """会话路由器。

    管理 Supervisor 与 SubAgent 之间的会话映射关系。
    """

    def __init__(self) -> None:
        self._routes: dict[str, SessionRoute] = {}

    @staticmethod
    def build_main_key(agent_id: str) -> str:
        """构建 Supervisor 主会话键。"""
        return f"agent:{agent_id}:main"

    @staticmethod
    def build_subagent_key(supervisor_id: str, subagent_id: str) -> str:
        """构建 SubAgent 子会话键。"""
        return f"agent:{supervisor_id}:subagent:{subagent_id}"

    def create_main_session(self, agent_id: str) -> SessionRoute:
        """创建 Supervisor 主会话路由。"""
        key = self.build_main_key(agent_id)
        route = SessionRoute(
            session_key=key,
            agent_id=agent_id,
            parent_session_key=None,
            depth=0,
        )
        self._routes[key] = route
        return route

    def create_subagent_session(
        self, supervisor_id: str, subagent_id: str, parent_key: str | None = None
    ) -> SessionRoute:
        """创建 SubAgent 子会话路由。"""
        key = self.build_subagent_key(supervisor_id, subagent_id)
        main_key = self.build_main_key(supervisor_id)
        parent = parent_key or main_key

        # 计算嵌套深度
        parent_route = self._routes.get(parent)
        depth = (parent_route.depth + 1) if parent_route else 1

        route = SessionRoute(
            session_key=key,
            agent_id=subagent_id,
            parent_session_key=parent,
            depth=depth,
        )
        self._routes[key] = route
        return route

    def get_route(self, session_key: str) -> SessionRoute | None:
        """获取会话路由。"""
        return self._routes.get(session_key)

    def get_children(self, parent_key: str) -> list[SessionRoute]:
        """获取子会话路由列表。"""
        return [r for r in self._routes.values() if r.parent_session_key == parent_key]

    def close_session(self, session_key: str) -> None:
        """关闭会话。"""
        route = self._routes.get(session_key)
        if route:
            route.status = "closed"

    def list_active(self) -> list[SessionRoute]:
        """列出所有活跃会话。"""
        return [r for r in self._routes.values() if r.status != "closed"]
