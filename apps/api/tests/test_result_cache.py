"""结果缓存测试。"""

from apps.api.app.services.result_cache import ResultCache


def test_cache_put_and_get() -> None:
    """写入后应可命中缓存。"""
    cache = ResultCache(max_size=10)
    cache.put("llm", {"prompt": "hello"}, {"text": "world"})

    entry = cache.get("llm", {"prompt": "hello"})
    assert entry is not None
    assert entry.value == {"text": "world"}
    assert entry.hit_count == 1

    stats = cache.stats()
    assert stats["total_hits"] == 1
    assert stats["size"] == 1


def test_cache_miss() -> None:
    """不存在的缓存应返回 None。"""
    cache = ResultCache(max_size=10)
    entry = cache.get("llm", {"prompt": "nonexistent"})
    assert entry is None

    stats = cache.stats()
    assert stats["total_misses"] == 1


def test_cache_eviction() -> None:
    """超出容量时应淘汰最早的缓存。"""
    cache = ResultCache(max_size=3)
    for i in range(5):
        cache.put("llm", {"id": i}, {"value": i})

    assert cache.stats()["size"] == 3
    assert cache.get("llm", {"id": 0}) is None
    assert cache.get("llm", {"id": 1}) is None
    assert cache.get("llm", {"id": 4}) is not None


def test_cache_invalidate() -> None:
    """主动失效应删除对应缓存。"""
    cache = ResultCache(max_size=10)
    cache.put("rag", {"query": "test"}, {"chunks": []})
    assert cache.invalidate("rag", {"query": "test"}) is True
    assert cache.get("rag", {"query": "test"}) is None


def test_cache_invalidate_by_prefix() -> None:
    """按类型批量失效。"""
    cache = ResultCache(max_size=10)
    cache.put("llm", {"a": 1}, "r1")
    cache.put("llm", {"a": 2}, "r2")
    cache.put("rag", {"a": 3}, "r3")

    removed = cache.invalidate_by_prefix("llm")
    assert removed == 2
    assert cache.stats()["size"] == 1
