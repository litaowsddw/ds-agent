"""Harmes 反馈循环 - 自动化运行分析 → 改进建议 → Skill 自动进化。

Harmes 反馈循环是 Skill Evolver 的调度层，负责：
1. 定期触发进化检查（Celery Beat 或手动触发）
2. 收集 Agent 运行指标
3. 调用 Skill Evolver 执行进化
4. 验证进化结果
5. 自动应用高置信度的进化
6. 低置信度进化需要人工审批

进化策略：
- 自动模式：置信度 >= 0.8 的进化自动应用
- 半自动模式：置信度 >= 0.8 自动应用，0.5-0.8 需审批
- 手动模式：所有进化都需要审批
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from packages.runtime.skill_evolver import (
    EvolutionAction,
    EvolutionRecord,
    EvolutionStatus,
    HarmesSkillEvolver,
    RunAnalysis,
)


class EvolutionPolicy(StrEnum):
    """进化策略。"""
    AUTO = "auto"           # 自动应用所有进化
    SEMI_AUTO = "semi_auto"  # 高置信度自动，低置信度需审批
    MANUAL = "manual"        # 全部需要审批


@dataclass(slots=True)
class FeedbackLoopConfig:
    """反馈循环配置。"""
    # evolution_policy 是进化策略
    evolution_policy: EvolutionPolicy = EvolutionPolicy.SEMI_AUTO
    # auto_apply_threshold 是自动应用的置信度阈值
    auto_apply_threshold: float = 0.8
    # max_evolution_per_cycle 是每次循环最大进化数
    max_evolution_per_cycle: int = 5
    # min_runs_for_analysis 是分析所需的最少运行次数
    min_runs_for_analysis: int = 10
    # cooldown_hours 是两次进化之间的冷却时间（小时）
    cooldown_hours: int = 24
    # rollback_on_failure 是进化失败后是否自动回滚
    rollback_on_failure: bool = True


@dataclass(slots=True)
class FeedbackLoopResult:
    """反馈循环结果。"""
    # agent_id 是 Agent ID
    agent_id: str
    # org_id 是组织 ID
    org_id: str
    # analysis 是运行分析
    analysis: RunAnalysis | None = None
    # evolution_records 是进化记录
    evolution_records: list[EvolutionRecord] = list
    # applied_count 是已应用的进化数
    applied_count: int = 0
    # pending_approval_count 是待审批的进化数
    pending_approval_count: int = 0
    # failed_count 是失败的进化数
    failed_count: int = 0
    # skipped_reason 是跳过的原因
    skipped_reason: str = ""


class FeedbackLoop:
    """Harmes 反馈循环调度器。"""

    def __init__(
        self,
        evolver: HarmesSkillEvolver | None = None,
        config: FeedbackLoopConfig | None = None,
    ) -> None:
        self.evolver = evolver or HarmesSkillEvolver()
        self.config = config or FeedbackLoopConfig()
        # 最近进化时间（用于冷却）
        self._last_evolution_time: dict[str, str] = {}
        # 待审批的进化记录
        self._pending_approvals: dict[str, EvolutionRecord] = {}

    async def run_cycle(self, agent_id: str, org_id: str) -> FeedbackLoopResult:
        """执行一次反馈循环。

        参数：
            agent_id: Agent ID
            org_id: 组织 ID

        返回：
            FeedbackLoopResult: 循环结果
        """
        result = FeedbackLoopResult(agent_id=agent_id, org_id=org_id)

        # 1. 检查冷却时间
        if not self._check_cooldown(agent_id):
            result.skipped_reason = "冷却期内，跳过本次进化"
            return result

        # 2. 分析运行历史
        analysis = await self.evolver.analyze(agent_id, org_id)
        result.analysis = analysis

        # 3. 检查是否有足够的运行数据
        if analysis.total_runs < self.config.min_runs_for_analysis:
            result.skipped_reason = f"运行数据不足（{analysis.total_runs}/{self.config.min_runs_for_analysis}）"
            return result

        # 4. 检查是否有改进机会
        if not analysis.improvement_opportunities:
            result.skipped_reason = "未发现改进机会"
            return result

        # 5. 执行进化
        evolution_records = await self.evolver.evolve(agent_id, org_id)
        result.evolution_records = evolution_records[:self.config.max_evolution_per_cycle]

        # 6. 应用进化
        for record in result.evolution_records:
            if record.status != EvolutionStatus.SUCCEEDED:
                result.failed_count += 1
                continue

            if self._should_auto_apply(record):
                # 自动应用
                applied = await self.evolver.apply_evolution(record)
                if applied:
                    record.status = EvolutionStatus.SUCCEEDED
                    result.applied_count += 1
                else:
                    if self.config.rollback_on_failure:
                        record.status = EvolutionStatus.ROLLED_BACK
                    result.failed_count += 1
            else:
                # 需要审批
                self._pending_approvals[record.record_id] = record
                result.pending_approval_count += 1

        return result

    async def approve_evolution(self, record_id: str) -> bool:
        """审批一条待审进化记录。

        参数：
            record_id: 进化记录 ID

        返回：
            bool: 是否成功应用
        """
        record = self._pending_approvals.pop(record_id, None)
        if not record:
            return False

        applied = await self.evolver.apply_evolution(record)
        if applied:
            record.status = EvolutionStatus.SUCCEEDED
        else:
            record.status = EvolutionStatus.FAILED
        return applied

    async def reject_evolution(self, record_id: str) -> bool:
        """拒绝一条待审进化记录。"""
        record = self._pending_approvals.pop(record_id, None)
        if not record:
            return False

        record.status = EvolutionStatus.ROLLED_BACK
        return True

    def get_pending_approvals(self, agent_id: str | None = None) -> list[EvolutionRecord]:
        """获取待审批的进化记录。"""
        records = list(self._pending_approvals.values())
        if agent_id:
            records = [r for r in records if r.agent_id == agent_id]
        return records

    def _check_cooldown(self, agent_id: str) -> bool:
        """检查冷却时间。"""
        from datetime import datetime, timedelta

        last_time = self._last_evolution_time.get(agent_id)
        if not last_time:
            return True

        try:
            last_dt = datetime.fromisoformat(last_time)
            cooldown = timedelta(hours=self.config.cooldown_hours)
            return datetime.utcnow() - last_dt >= cooldown
        except (ValueError, TypeError):
            return True

    def _should_auto_apply(self, record: EvolutionRecord) -> bool:
        """判断是否应该自动应用进化。"""
        if self.config.evolution_policy == EvolutionPolicy.AUTO:
            return True
        elif self.config.evolution_policy == EvolutionPolicy.SEMI_AUTO:
            return record.confidence >= self.config.auto_apply_threshold
        else:
            return False
