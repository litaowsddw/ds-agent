"""Redis 异步客户端配置。

提供全局 Redis 连接池和常用操作封装。
使用 redis[hiredis] 实现高性能异步访问。
"""

from __future__ import annotations

import os
import json
from typing import Any

try:
    from redis.asyncio import Redis, ConnectionPool
except ImportError:
    Redis = None
    ConnectionPool = None


# Redis 连接配置 - 从环境变量读取
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# 全局连接池
_pool: ConnectionPool | None = None


def get_redis_pool() -> ConnectionPool:
    """获取或创建 Redis 连接池。"""
    global _pool
    if _pool is None and ConnectionPool is not None:
        _pool = ConnectionPool.from_url(REDIS_URL, decode_responses=True)
    return _pool


def get_redis() -> Redis:
    """获取 Redis 客户端实例。"""
    if Redis is None:
        raise RuntimeError("redis 库未安装，请执行 pip install redis[hiredis]")
    return Redis(connection_pool=get_redis_pool())


class RedisClient:
    """Redis 异步客户端封装。

    提供常用的缓存、限流、分布式锁等操作。
    所有方法均为 async，适合在 FastAPI 异步路由中使用。
    """

    def __init__(self, redis: Redis | None = None) -> None:
        # _redis 是底层 Redis 客户端。
        self._redis = redis

    async def _get_redis(self) -> Redis:
        """获取 Redis 客户端，延迟初始化。"""
        if self._redis is None:
            self._redis = get_redis()
        return self._redis

    # ── 缓存操作 ──

    async def get(self, key: str) -> str | None:
        """读取缓存值。"""
        r = await self._get_redis()
        return await r.get(key)

    async def get_json(self, key: str) -> Any | None:
        """读取 JSON 缓存值。"""
        val = await self.get(key)
        if val is None:
            return None
        return json.loads(val)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        """写入缓存值。ex 是过期秒数。"""
        r = await self._get_redis()
        await r.set(key, value, ex=ex)

    async def set_json(self, key: str, value: Any, ex: int | None = None) -> None:
        """写入 JSON 缓存值。"""
        await self.set(key, json.dumps(value, ensure_ascii=False), ex=ex)

    async def delete(self, *keys: str) -> int:
        """删除缓存键，返回删除数量。"""
        r = await self._get_redis()
        return await r.delete(*keys)

    async def exists(self, key: str) -> bool:
        """检查键是否存在。"""
        r = await self._get_redis()
        return bool(await r.exists(key))

    async def keys(self, pattern: str) -> list[str]:
        """按模式扫描键。"""
        r = await self._get_redis()
        return await r.keys(pattern)

    async def expire(self, key: str, seconds: int) -> bool:
        """设置过期时间。"""
        r = await self._get_redis()
        return await r.expire(key, seconds)

    async def ttl(self, key: str) -> int:
        """获取剩余 TTL。"""
        r = await self._get_redis()
        return await r.ttl(key)

    # ── Hash 操作 ──

    async def hget(self, name: str, key: str) -> str | None:
        """读取 Hash 字段。"""
        r = await self._get_redis()
        return await r.hget(name, key)

    async def hset(self, name: str, key: str, value: str) -> int:
        """写入 Hash 字段。"""
        r = await self._get_redis()
        return await r.hset(name, key, value)

    async def hgetall(self, name: str) -> dict[str, str]:
        """读取 Hash 全部字段。"""
        r = await self._get_redis()
        return await r.hgetall(name)

    # ── 限流操作 ──

    async def eval_script(self, script: str, keys: list[str], args: list[Any]) -> Any:
        """执行 Lua 脚本。"""
        r = await self._get_redis()
        return await r.eval(script, len(keys), *keys, *args)

    # ── 分布式锁 ──

    async def acquire_lock(self, lock_key: str, timeout: int = 30) -> bool:
        """尝试获取分布式锁。"""
        r = await self._get_redis()
        # 使用 SETNX 实现简单分布式锁
        return bool(await r.set(lock_key, "1", nx=True, ex=timeout))

    async def release_lock(self, lock_key: str) -> None:
        """释放分布式锁。"""
        await self.delete(lock_key)

    # ── 健康检查 ──

    async def ping(self) -> bool:
        """检查 Redis 连接是否正常。"""
        try:
            r = await self._get_redis()
            return await r.ping()
        except Exception:
            return False


# 全局 Redis 客户端实例
redis_client = RedisClient()
