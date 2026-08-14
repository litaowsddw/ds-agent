"""Fresh-agent iteration loop — models DeepSeek Harness ``dsh-ralph``.

A ``RalphLoop`` runs a bounded sequence of fresh rounds toward one immutable
objective.  Each round opens with no conversation seed: the only durable state
is a workspace memory that the previous round's report replaces.  The loop
stops when a round reports completion or a concrete blocker, or at the round
limit.  The per-round agent is injected by the runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable


@dataclass(frozen=True, slots=True)
class RalphRoundResult:
    """One fresh round's bounded, structured report."""

    status: str  # completed | blocked | continue
    report: str
    blocker_reason: str | None = None


@dataclass(frozen=True, slots=True)
class RalphReport:
    """The loop's terminal result."""

    status: str  # completed | blocked | round_limit
    rounds: int
    final_report: str | None
    blocker_reason: str | None


RunRoundFn = Callable[[int, str, str], Awaitable[RalphRoundResult] | RalphRoundResult]


class RalphLoop:
    """Drive a fresh-agent iteration loop with durable workspace memory."""

    def __init__(self, run_round: RunRoundFn, *, max_rounds: int = 8) -> None:
        self.run_round = run_round
        self.max_rounds = max(1, int(max_rounds))

    async def run(self, objective: str) -> RalphReport:
        memory = ""
        for round_index in range(1, self.max_rounds + 1):
            result = await self.run_round(round_index, objective, memory)
            if result.status == "completed":
                return RalphReport("completed", round_index, result.report, None)
            if result.status == "blocked":
                return RalphReport(
                    "blocked", round_index, result.report, result.blocker_reason
                )
            memory = str(result.report or "").strip()
        return RalphReport("round_limit", self.max_rounds, memory or None, None)
