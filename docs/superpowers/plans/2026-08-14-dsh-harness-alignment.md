# DSH Harness 对齐方案

目标：参照 DeepSeek Harness（`@deepseek-ai/dsh`，即本仓库开发时正在运行的 agent harness）的
agent-plane 设计，把 AgentFlow 的 agent 运行时对齐到同等的"编码 agent harness"能力面。

## 1. DSH harness 参考架构（agent-plane）

DSH 用 Cordis 插件体系把 harness 拆成可组合的 agent-plane 行，`standard` preset
（`config/agent-presets/standard/agent.cordis.yml`）挂载了完整能力面：

| 域 | 插件 | 语义 |
|---|---|---|
| persona | `dsh-persona` | "You are a coding agent powered by {{model}}…" |
| 指令 | `dsh-agent-instructions` | 64KB 稳定指令契约（工具语义、目标、沙箱、编排规则） |
| shell | `dsh-tool-bash` / `dsh-tool-pwsh` | 平台相关 shell，sandbox 执行 |
| 文件系统 | `dsh-tool-fs` + `dsh-tool-fs-search` | read/write/edit + glob/grep |
| 后台任务 | `dsh-tool-jobs` | run_in_background + job_output/kill/list |
| 技能 | `dsh-skill` + `dsh-skill-filesystem` + `dsh-tool-skill` | registry + 文件系统发现 + loader |
| 目标 | `dsh-goal` + `dsh-goal-round-driver` + `dsh-tool-goal` | create/get/update，edit/pause/resume/complete/blocked，轮次驱动 |
| 计划模式 | `dsh-plan-mode` | exit_plan_mode，只读探索，决策完备的计划 |
| 压缩 | `dsh-compaction-basic` + `dsh-compaction-tool-result-pruner` + `dsh-command-compact` | 上下文压缩 + 工具结果裁剪（head/tail/阈值） |
| 委派 | `dsh-tool-subagent`(spawn/fork/codex/claude) + `dsh-tool-subagent-control`(list/send/interrupt) | 后台子代理 + 可续会话 |
| 编排 | `dsh-tool-workflow` + `dsh-workflow-worker-thread` | 大规模多代理 fan-out（agent/pipeline/parallel） |
| 迭代 | `dsh-tool-ralph` | 全新 agent 迭代循环，工作区作为持久记忆 |
| 其余 | `dsh-tool-ask-user` / `dsh-tool-todo` / `dsh-tool-web` | 提问 / 任务清单 / 联网搜索 |
| 沙箱 | `dsh-sandbox` + `dsh-sandbox-windows-acl` + `dsh-permission-presets` | workspace-write / danger-full-access / read-only + 审批策略 |

## 2. AgentFlow 当前状态（agent-plane）

| 域 | 现状 | 文件 |
|---|---|---|
| 指令契约 | 5 条平台规则 + 角色契约 + supervisor 契约（偏薄） | `packages/runtime/system_prompt.py` |
| 工具 | 6 个只读/知识工具：knowledge_list/search、memory_recall、skill_search/create、MCP(low-risk) | `packages/runtime/tools/` |
| 子代理 | 静态 kind 注册表（SUPERVISOR/USER_SUB/SYSTEM_SKILL/RAG/TOOL），无 spawn/fork/可续 | `packages/runtime/subagent.py` |
| 上下文 | MVP 骨架（assemble/compact 多为桩） | `packages/runtime/context_engine.py` |
| 编译 | prefix-cache 友好（已对齐 DSH compaction/session-projection 思想） | `packages/runtime/prompt_compiler.py` |
| 编排 | LangGraph Supervisor(plan→delegate→reflect→respond) + ReAct SubAgent | `langgraph_supervisor.py` / `langgraph_executor.py` |
| 进化 | Hermes skill evolver + feedback loop | `skill_evolver.py` / `feedback_loop.py` |
| 沙箱 | 无 agent 工具沙箱；仅有 RBAC + 高风险 MCP 审批 | `services/rbac.py` |
| 目标/计划 | 无 goal 生命周期、无 plan mode | — |

## 3. 差距与分阶段路线

### Phase 1 — 指令契约对齐（本轮，自包含）
把 `system_prompt.py` 从 5 条规则扩展为 DSH 式完整指令契约，并新增"工具目录"渲染：
- persona + 稳定平台契约（证据优先、不可信数据、最小充分能力、审批、不伪造、保密、先答后证）
- 能力协议（工具目录诚实呈现、一次一个作用域调用、复用观察、失败换安全替代）
- 目标/计划/压缩/委派/编排语义（诚实映射到 AgentFlow 现有能力）
- `render_tool_catalog()` 从实际注册表注入可用工具，避免"声称不存在的能力"
- 保持现有回归标记（`[AgentFlow platform contract]`、`Do not invent tool calls`、
  `Never emit fake function-call syntax`）

### Phase 2 — 默认工具集扩展
新增 DSH 等价工具到 `packages/runtime/tools/`（每个都需对应后端服务）：
- ✅ `todo_write`（对齐 `dsh-tool-todo`，纯状态、全量替换、可注入 store）
- ✅ `web_search`（对齐 `dsh-tool-web`，可注入 search accessor，未配置时诚实报错）
- ✅ `list_subagents`（对齐 `dsh-tool-subagent-control/list-agents`，可注入 lister）
- ✅ `goal`（create_goal/get_goal/update_goal，对齐 `dsh-tool-goal`，包装 `GoalManager`）
- ✅ `exit_plan_mode`（对齐 `dsh-plan-mode`，包装 `PlanModeManager`）
- ✅ `spawn_subagent`（对齐 `dsh-tool-subagent` spawn，可注入 subagent_executor）
- ✅ `fs`（read_file/write_file/edit_file/glob_files/grep_files，对齐 `dsh-tool-fs` +
  `dsh-tool-fs-search` + `dsh-tool-str-replace-editor`，可注入 `LocalFilesystem`，路径越界拒绝 + read_only 标记）
- ✅ `ask_user`（对齐 `dsh-tool-ask-user`，可注入 ask_user_accessor）
- ✅ `jobs`（list_jobs/read_job_output/kill_job，对齐 `dsh-tool-jobs`，包装 `JobRegistry`）
- ✅ `shell`（对齐 `dsh-tool-bash`/`dsh-tool-pwsh`，可注入 shell_executor，`EXTERNAL` 档）
- ✅ `ralph`（对齐 `dsh-tool-ralph`，包装 `RalphLoop` fresh-agent 循环，`WRITE` 档）
- ✅ `workflow`（对齐 `dsh-tool-workflow`，安全声明式 fan-out：phase 内并行、phase 间串行，
  包装 `WorkflowRunner`，`WRITE` 档）

### Phase 3 — 编排原语
- ✅ Goal 生命周期域（`packages/runtime/goal.py`：Goal 不可变快照 + GoalManager，
  create/get/update 五动作、乐观并发 revision、blocked 轮次门槛、disarm）
- ✅ Goal 轮次驱动（`goal_round_driver.py`：armed/max_rounds/complete/blocked 循环）
- ✅ Plan mode（`PlanModeManager` + `PLAN_MODE_CONTRACT` 注入 + `exit_plan_mode` 工具）
- ✅ 结构化压缩（`CompactionManager`：阈值判断 + head 摘要 + keep_tail）+ 工具结果 head/tail 裁剪
- ✅ 子代理 spawn/fork（`spawn_subagent` + `subagent_fork`；可续会话 send_message/interrupt 未做）
- ✅ Ralph 循环（`RalphLoop`：fresh-agent 每轮无会话种子、workspace 作持久记忆）
- ✅ Workflow fan-out（`WorkflowRunner`：phase 并行 + pipeline 无 barrier；`WorkflowTool` 声明式）

### Phase 4 — 沙箱/权限模型
把工具权限/审批对齐 DSH 三档（workspace-write / danger-full-access / read-only）+ 审批策略，
与现有 RBAC 结合。

- ✅ `packages/runtime/permissions.py`：`SandboxMode`(read-only/workspace-write/danger-full-access)
  + `ToolPermission`(read/write/external) + 工具名→权限映射 + `allows()` 三档判定
- ✅ `build_system_tools` 新增 `sandbox_mode` 参数，按档位过滤工具目录
- ✅ `packages/runtime/shell_executor.py`：`LocalShellExecutor`（subprocess + cwd 隔离 + 超时）
- ✅ `packages/runtime/approval.py`：`ApprovalPolicy`（ask/never，EXTERNAL 档需审批）
- ⬜ 审批策略接线到 RBAC（运行时集成）

## 4. 验收标准
- Phase 1：`pytest` 全绿；新契约被 `build_agent_system_prompt` / `build_subagent_system_prompt` 使用；
  工具目录只列出实际注入的工具。
- Phase 2-4：每个新工具/原语有独立单测；高风险路径走审批；全量回归绿。
