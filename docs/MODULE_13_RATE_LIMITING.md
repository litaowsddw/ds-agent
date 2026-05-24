# 模块 13：全局限流与并发控制 MVP

## 1. 模块目标

模块 13 建立 Gateway 调用前的统一限流入口：

- token bucket 抽象。
- 本地内存 fallback 限流器。
- Provider / Model / Scope 三维限流 key。
- Gateway 调用前限流检查。
- 限流失败写入 LLM 调用日志。

## 2. 当前实现

核心代码：

```text
apps/api/app/gateway/rate_limiter.py
apps/api/app/gateway/llm.py
```

当前限流 key：

```text
llm:provider:{provider}
llm:model:{provider}:{model}
llm:scope:{scope}
```

其中 `scope` 当前默认是 `global`，后续会扩展为：

- `org:{org_id}`
- `agent:{agent_id}`
- `workflow:{workflow_id}`
- `user:{user_id}`

## 3. 当前限制

MVP 使用本地内存令牌桶，只对单 API 进程有效。生产环境需要替换成 Redis Lua：

- 多 worker 全局一致。
- 原子扣减。
- 支持不同租户不同额度。
- 支持令牌等待和延迟重试。

## 4. 测试

测试文件：

```text
apps/api/tests/test_rate_limiter.py
```

覆盖场景：

- 令牌桶耗尽后拒绝请求。
- Gateway 被限流时记录失败日志。

## 5. 下一步

模块 14：Memory Manager MVP。

计划新增：

- 长期记忆写入。
- 按 org/agent 隔离召回。
- Memory 与 Context Engine 集成。

