"""本地持久化状态文件。

该模块为 MVP 提供一个轻量的本地持久化层，避免用户创建的组织、Agent、
Workflow、模型供应商和运行记录在 API 重启后丢失。它不是最终数据库方案，
后续可以替换为 PostgreSQL Repository，而不改变上层 Store 的业务接口。
"""

from __future__ import annotations

import os
import pickle
from pathlib import Path
from threading import RLock
from typing import Any


class LocalStateStore:
    """按 bucket 保存 Python 对象的本地状态文件。"""

    def __init__(self) -> None:
        # enabled 表示是否启用本地持久化；测试环境会显式关闭。
        self.enabled = os.getenv("AGENTFLOW_PERSISTENCE", "1") == "1"

        # file_path 是持久化文件路径，默认保存在仓库工作目录下的 .agentflow 目录。
        self.file_path = Path(os.getenv("AGENTFLOW_STATE_FILE", ".agentflow/state.pkl"))

        # lock 保证同一进程内多 Store 写入状态文件时不会互相覆盖。
        self.lock = RLock()

        # state 保存所有 bucket 的内存副本。
        self.state: dict[str, Any] = self._load_state()

    def load_bucket(self, bucket_name: str, default: Any) -> Any:
        """读取指定 bucket，缺失时返回调用方提供的默认值。"""

        if not self.enabled:
            return default
        with self.lock:
            return self.state.get(bucket_name, default)

    def save_bucket(self, bucket_name: str, value: Any) -> None:
        """保存指定 bucket 并立即落盘。"""

        if not self.enabled:
            return
        with self.lock:
            self.state[bucket_name] = value
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with self.file_path.open("wb") as file:
                pickle.dump(self.state, file)

    def _load_state(self) -> dict[str, Any]:
        """从磁盘加载完整状态。"""

        if not self.enabled or not self.file_path.exists():
            return {}
        try:
            with self.file_path.open("rb") as file:
                loaded_state = pickle.load(file)
        except Exception:
            return {}
        if isinstance(loaded_state, dict):
            return loaded_state
        return {}


# local_state_store 是 API 进程内共享的本地持久化状态。
local_state_store = LocalStateStore()
