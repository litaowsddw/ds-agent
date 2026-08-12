"""Harmes 反馈循环的门控与冷却行为测试。"""

import pytest

from packages.runtime.feedback_loop import (
    EvolutionPolicy,
    FeedbackLoop,
    FeedbackLoopConfig,
)
from packages.runtime.skill_evolver import (
    EvolutionAction,
    EvolutionRecord,
    EvolutionStatus,
    RunAnalysis,
)


class FakeEvolver:
    """记录调用并可配置结果的 Skill Evolver 替身。"""

    def __init__(self, *, total_runs: int = 20, opportunities: int = 1,
                 records: list[EvolutionRecord] | None = None, apply_ok: bool = True) -> None:
        self._total_runs = total_runs
        self._opportunities = opportunities
        self._records = records or []
        self._apply_ok = apply_ok
        self.applied: list[str] = []

    async def analyze(self, agent_id: str, org_id: str) -> RunAnalysis:
        return RunAnalysis(
            agent_id=agent_id,
            total_runs=self._total_runs,
            improvement_opportunities=[{"kind": "test"}] * self._opportunities,
        )

    async def evolve(self, agent_id: str, org_id: str) -> list[EvolutionRecord]:
        return list(self._records)

    async def apply_evolution(self, record: EvolutionRecord) -> bool:
        if self._apply_ok:
            self.applied.append(record.record_id)
        return self._apply_ok


def make_record(record_id: str, confidence: float) -> EvolutionRecord:
    return EvolutionRecord(
        record_id=record_id,
        agent_id="agent-1",
        org_id="org-1",
        action=EvolutionAction.CREATE,
        skill_name="demo-skill",
        reasoning="test",
        confidence=confidence,
        status=EvolutionStatus.SUCCEEDED,
    )


@pytest.mark.asyncio
async def test_cooldown_blocks_second_cycle() -> None:
    loop = FeedbackLoop(
        evolver=FakeEvolver(records=[make_record("rec-1", 0.9)]),
        config=FeedbackLoopConfig(evolution_policy=EvolutionPolicy.AUTO, cooldown_hours=24),
    )

    first = await loop.run_cycle("agent-1", "org-1")
    assert first.applied_count == 1

    second = await loop.run_cycle("agent-1", "org-1")
    assert second.skipped_reason == "冷却期内，跳过本次进化"
    assert second.applied_count == 0


@pytest.mark.asyncio
async def test_semi_auto_gates_low_confidence_evolutions_for_approval() -> None:
    loop = FeedbackLoop(
        evolver=FakeEvolver(records=[make_record("high", 0.9), make_record("low", 0.5)]),
        config=FeedbackLoopConfig(evolution_policy=EvolutionPolicy.SEMI_AUTO, auto_apply_threshold=0.8),
    )

    result = await loop.run_cycle("agent-1", "org-1")

    assert result.applied_count == 1
    assert result.pending_approval_count == 1
    pending = loop.get_pending_approvals("agent-1")
    assert [record.record_id for record in pending] == ["low"]


@pytest.mark.asyncio
async def test_cycle_skips_when_run_history_is_insufficient() -> None:
    loop = FeedbackLoop(
        evolver=FakeEvolver(total_runs=2),
        config=FeedbackLoopConfig(min_runs_for_analysis=10),
    )

    result = await loop.run_cycle("agent-1", "org-1")

    assert "运行数据不足" in result.skipped_reason
    assert result.evolution_records == []


@pytest.mark.asyncio
async def test_failed_auto_apply_rolls_back_when_enabled() -> None:
    loop = FeedbackLoop(
        evolver=FakeEvolver(records=[make_record("rec-1", 0.95)], apply_ok=False),
        config=FeedbackLoopConfig(evolution_policy=EvolutionPolicy.AUTO, rollback_on_failure=True),
    )

    result = await loop.run_cycle("agent-1", "org-1")

    assert result.failed_count == 1
    assert result.evolution_records[0].status == EvolutionStatus.ROLLED_BACK
