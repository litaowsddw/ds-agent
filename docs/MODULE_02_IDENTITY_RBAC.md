# 模块 2：用户、组织、群组、权限隔离

## 1. 模块目标

模块 2 建立 AgentFlow 的多租户基础：

- 用户注册和登录校验。
- 组织创建。
- 群组创建。
- 成员关系和组织角色。
- RBAC 权限判断。
- 审计日志。
- 组织级越权访问拦截。

## 2. 当前实现范围

MVP 阶段使用进程内存存储，目标是先稳定业务边界和权限逻辑。后续数据库模块会把
`IdentityStore` 替换为 SQLAlchemy Repository。

已实现 API：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/identity/users/register` | 注册用户 |
| POST | `/identity/users/login` | 登录校验 |
| POST | `/identity/organizations` | 创建组织 |
| GET | `/identity/users/{user_id}/organizations` | 查看用户所属组织 |
| POST | `/identity/organizations/{org_id}/teams` | 创建群组 |
| GET | `/identity/organizations/{org_id}/teams` | 查看组织群组 |
| POST | `/identity/organizations/{org_id}/members` | 添加成员 |
| GET | `/identity/organizations/{org_id}/audit-logs` | 查看审计日志 |

## 3. 角色权限

| 角色 | 权限 |
| --- | --- |
| owner | 全部权限 |
| admin | 管理组织、群组、Agent、Workflow、审计 |
| developer | 读取组织、读取群组、创建 Agent、创建 Workflow |
| viewer | 读取组织、读取群组 |

权限定义位于：

```text
apps/api/app/services/rbac.py
```

## 4. 核心目录

```text
apps/api/app/domain/identity.py
  用户、组织、群组、成员关系、审计日志领域模型

apps/api/app/services/rbac.py
  RBAC 权限服务

apps/api/app/services/identity_store.py
  MVP 身份与租户内存存储

apps/api/app/schemas/identity.py
  身份 API 请求和响应模型

apps/api/app/routes/identity.py
  身份与租户 API 路由
```

## 5. 隔离原则

- 所有组织资源必须带 `org_id`。
- 操作者必须在目标组织内有 membership。
- 资源写入动作必须经过 RBAC。
- 审计日志不能写入密码、密钥等敏感信息。
- 后续 Agent、Workflow、Skill、MCP、Memory 必须复用该组织边界。

## 6. 测试

测试文件：

```text
apps/api/tests/test_identity_store.py
apps/api/tests/test_identity_api.py
```

覆盖场景：

- owner 可以创建群组和添加成员。
- viewer 不能创建群组。
- 用户不能读取未加入组织的群组。
- API 主链路可运行。
- API 跨组织访问返回 403。

## 7. 下一步

模块 3 将实现 Agent 管理与 Workspace：

- Agent 绑定组织和群组。
- Agent Workspace 文件模型。
- Agent 可用 Skill/MCP/Memory 的隔离边界。
- Agent 创建权限接入 RBAC。

