"""Harmes Skill Evolver - Agent 自我进化引擎。

Harmes 的核心理念：Agent 通过对自身运行历史的反思，自动发现改进机会，
生成新的 Skill 或优化已有 Skill，实现持续进化。

进化循环：
1. Analyze - 分析 Agent 的运行历史（Session、Workflow Run、LLM Call）
2. Reflect - 识别改进机会（重复模式、低效操作、用户反馈）
3. Evolve - 生成或更新 SKILL.md
4. Validate - 验证新 Skill 的有效性
5. Deploy - 部署新 Skill 到 Agent Workspace

v0.3 实现范围：
- Analyze + Reflect + Evolve 核心
- Skill 版本管理
- 进化历史追踪
- LLM 驱动的 Skill 生成
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol


class EvolutionAction(StrEnum):
    """进化动作类型。"""
    CREATE = "create"       # 创建新 Skill
    UPDATE = "update"       # 更新已有 Skill
    DEPRECATE = "deprecate"  # 废弃 Skill
    MERGE = "merge"         # 合并多个 Skill


class EvolutionStatus(StrEnum):
    """进化状态。"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass(slots=True)
class EvolutionRecord:
    """一条进化记录。"""
    # record_id 是进化记录唯一标识
    record_id: str
    # agent_id 是进化的 Agent ID
    agent_id: str
    # org_id 是组织 ID
    org_id: str
    # action 是进化动作
    action: EvolutionAction
    # skill_name 是涉及的 Skill 名称
    skill_name: str
    # reasoning 是进化推理过程
    reasoning: str
    # skill_content 是生成/更新的 SKILL.md 内容
    skill_content: str = ""
    # previous_version 是更新前的版本
    previous_version: str = ""
    # new_version 是更新后的版本
    new_version: str = "1.0.0"
    # confidence 是进化置信度（0-1）
    confidence: float = 0.0
    # status 是进化状态
    status: EvolutionStatus = EvolutionStatus.PENDING
    # error_message 是错误信息
    error_message: str = ""
    # analysis_data 是分析数据摘要
    analysis_data: dict[str, Any] = field(default_factory=dict)
    # created_at 是创建时间
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    # applied_at 是应用时间
    applied_at: str = ""


@dataclass(slots=True)
class RunAnalysis:
    """运行分析结果。"""
    # agent_id 是分析的 Agent ID
    agent_id: str
    # total_runs 是分析的运行总数
    total_runs: int = 0
    # success_rate 是成功率
    success_rate: float = 0.0
    # common_patterns 是常见模式
    common_patterns: list[dict[str, Any]] = field(default_factory=list)
    # failure_patterns 是失败模式
    failure_patterns: list[dict[str, Any]] = field(default_factory=list)
    # improvement_opportunities 是改进机会
    improvement_opportunities: list[dict[str, Any]] = field(default_factory=list)
    # user_feedback_summary 是用户反馈摘要
    user_feedback_summary: str = ""


class LLMCaller(Protocol):
    """LLM 调用协议。"""
    async def call(self, prompt: str, system_prompt: str = "",
                   temperature: float = 0.3, max_tokens: int = 2048) -> str: ...


class DBAccessor(Protocol):
    """数据库访问协议。"""
    async def get_agent_runs(self, agent_id: str, org_id: str, limit: int = 50) -> list[dict[str, Any]]: ...
    async def get_agent_messages(self, agent_id: str, org_id: str, limit: int = 100) -> list[dict[str, Any]]: ...
    async def get_skills(self, agent_id: str, org_id: str) -> list[dict[str, Any]]: ...
    async def save_skill(self, agent_id: str, org_id: str, skill_data: dict[str, Any]) -> dict[str, Any]: ...
    async def update_skill(self, skill_id: str, skill_data: dict[str, Any]) -> dict[str, Any]: ...
    async def save_evolution_record(self, record: EvolutionRecord) -> None: ...


# 分析 Prompt
ANALYZE_PROMPT = """你是一个 Agent 运行分析专家。分析以下 Agent 运行数据，识别改进机会。

运行数据：
{run_data}

现有 Skill：
{existing_skills}

请以 JSON 格式输出分析结果：
{{
  "success_rate": 0.0-1.0,
  "common_patterns": [
    {{"pattern": "模式描述", "frequency": 次数, "type": "success|failure|neutral"}}
  ],
  "failure_patterns": [
    {{"pattern": "失败模式", "frequency": 次数, "root_cause": "根因分析"}}
  ],
  "improvement_opportunities": [
    {{
      "type": "new_skill|update_skill|merge_skills|deprecate_skill",
      "description": "改进描述",
      "affected_skill": "受影响的 Skill 名称",
      "confidence": 0.0-1.0,
      "reasoning": "推理过程"
    }}
  ]
}}"""

# 进化 Prompt
EVOLVE_PROMPT = """你是一个 Skill Evolver。根据分析结果，生成或更新 SKILL.md 技能文件。

改进机会：
{opportunity}

相关运行数据：
{relevant_data}

现有 Skill 内容：
{existing_content}

请以 JSON 格式输出进化结果：
{{
  "action": "create|update|deprecate|merge",
  "skill_name": "技能名称",
  "skill_content": "完整的 SKILL.md 内容（包含 YAML front matter 和 Markdown 正文）",
  "reasoning": "进化推理过程",
  "confidence": 0.0-1.0,
  "version": "新版本号"
}}

SKILL.md 格式规范：
---
name: 技能名称
description: 技能描述
trigger_conditions:
  - 触发条件1
version: 1.0.0
author: harmes_skill_evolver
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
---

# 技能名称

## 步骤
1. 步骤1
2. 步骤2

## 示例
- 示例1

## 注意事项
- 注意事项1"""


class HarmesSkillEvolver:
    """Harmes Skill Evolver 核心。

    负责 Agent 的自我进化循环：Analyze → Reflect → Evolve → Validate → Deploy
    """

    def __init__(
        self,
        llm_caller: LLMCaller | None = None,
        db_accessor: DBAccessor | None = None,
    ) -> None:
        self.llm_caller = llm_caller
        self.db_accessor = db_accessor
        # 进化历史
        self._evolution_history: list[EvolutionRecord] = []

    async def evolve(self, agent_id: str, org_id: str) -> list[EvolutionRecord]:
        """执行一次完整的进化循环。

        参数：
            agent_id: Agent ID
            org_id: 组织 ID

        返回：
            本次进化产生的进化记录列表
        """
        # 1. Analyze - 分析运行历史
        analysis = await self.analyze(agent_id, org_id)

        if not analysis.improvement_opportunities:
            return []

        # 2. 对每个改进机会执行 Evolve
        records: list[EvolutionRecord] = []
        for opportunity in analysis.improvement_opportunities:
            record = await self.evolve_opportunity(agent_id, org_id, opportunity, analysis)
            if record:
                records.append(record)

        # 3. 保存进化记录
        for record in records:
            self._evolution_history.append(record)
            if self.db_accessor:
                try:
                    await self.db_accessor.save_evolution_record(record)
                except Exception:
                    pass

        return records

    async def analyze(self, agent_id: str, org_id: str) -> RunAnalysis:
        """分析 Agent 运行历史，识别改进机会。

        参数：
            agent_id: Agent ID
            org_id: 组织 ID

        返回：
            RunAnalysis: 分析结果
        """
        analysis = RunAnalysis(agent_id=agent_id)

        # 收集运行数据
        run_data: list[dict[str, Any]] = []
        messages: list[dict[str, Any]] = []
        existing_skills: list[dict[str, Any]] = []

        if self.db_accessor:
            try:
                run_data = await self.db_accessor.get_agent_runs(agent_id, org_id)
                messages = await self.db_accessor.get_agent_messages(agent_id, org_id)
                existing_skills = await self.db_accessor.get_skills(agent_id, org_id)
            except Exception:
                pass

        if not run_data and not messages:
            # 没有数据，返回空分析
            analysis.total_runs = 0
            analysis.success_rate = 0.0
            return analysis

        # 如果有 LLM，使用 LLM 分析
        if self.llm_caller:
            return await self._llm_analyze(agent_id, org_id, run_data, messages, existing_skills)

        # 降级：基于规则的分析
        return self._rule_based_analyze(agent_id, run_data, messages, existing_skills)

    async def evolve_opportunity(
        self,
        agent_id: str,
        org_id: str,
        opportunity: dict[str, Any],
        analysis: RunAnalysis,
    ) -> EvolutionRecord | None:
        """针对一个改进机会执行进化。

        参数：
            agent_id: Agent ID
            org_id: 组织 ID
            opportunity: 改进机会
            analysis: 运行分析结果

        返回：
            EvolutionRecord | None: 进化记录
        """
        import uuid

        record = EvolutionRecord(
            record_id=f"evo_{uuid.uuid4().hex[:12]}",
            agent_id=agent_id,
            org_id=org_id,
            action=EvolutionAction(opportunity.get("type", "create").replace("_skill", "").replace("new", "create")),
            skill_name=opportunity.get("affected_skill", "new_skill"),
            reasoning=opportunity.get("reasoning", ""),
            confidence=opportunity.get("confidence", 0.0),
            analysis_data={
                "total_runs": analysis.total_runs,
                "success_rate": analysis.success_rate,
                "opportunity": opportunity,
            },
        )

        if not self.llm_caller:
            record.status = EvolutionStatus.FAILED
            record.error_message = "LLM 调用器未配置，无法进化"
            return record

        try:
            # 获取现有 Skill 内容
            existing_content = ""
            if self.db_accessor:
                skills = await self.db_accessor.get_skills(agent_id, org_id)
                for skill in skills:
                    if skill.get("name") == record.skill_name:
                        existing_content = skill.get("content", "")
                        record.previous_version = skill.get("version", "0.0.0")
                        break

            # 构建 Evolve Prompt
            prompt = EVOLVE_PROMPT.format(
                opportunity=json.dumps(opportunity, ensure_ascii=False, indent=2),
                relevant_data=json.dumps(analysis.common_patterns[:5], ensure_ascii=False, indent=2),
                existing_content=existing_content or "无现有内容",
            )

            # 调用 LLM
            response_text = await self.llm_caller.call(
                prompt=prompt,
                system_prompt="",
                temperature=0.2,
                max_tokens=4096,
            )

            # 解析结果
            result = self._parse_json_response(response_text)
            if not result:
                record.status = EvolutionStatus.FAILED
                record.error_message = "LLM 输出解析失败"
                return record

            record.action = EvolutionAction(result.get("action", "create"))
            record.skill_name = result.get("skill_name", record.skill_name)
            record.skill_content = result.get("skill_content", "")
            record.reasoning = result.get("reasoning", record.reasoning)
            record.confidence = result.get("confidence", record.confidence)
            record.new_version = result.get("version", self._bump_version(record.previous_version))
            record.status = EvolutionStatus.SUCCEEDED

        except Exception as exc:
            record.status = EvolutionStatus.FAILED
            record.error_message = str(exc)

        return record

    async def apply_evolution(self, record: EvolutionRecord) -> bool:
        """应用一条进化记录到数据库。

        参数：
            record: 进化记录

        返回：
            bool: 是否成功
        """
        if not self.db_accessor:
            return False

        try:
            if record.action == EvolutionAction.CREATE:
                await self.db_accessor.save_skill(
                    record.agent_id,
                    record.org_id,
                    {
                        "name": record.skill_name,
                        "content": record.skill_content,
                        "version": record.new_version,
                        "source": "harmes_evolver",
                        "scope": "agent",
                    },
                )
            elif record.action == EvolutionAction.UPDATE:
                # 查找现有 Skill 并更新
                skills = await self.db_accessor.get_skills(record.agent_id, record.org_id)
                for skill in skills:
                    if skill.get("name") == record.skill_name:
                        await self.db_accessor.update_skill(
                            str(skill.get("skill_id", "")),
                            {
                                "content": record.skill_content,
                                "version": record.new_version,
                            },
                        )
                        break
            elif record.action == EvolutionAction.DEPRECATE:
                skills = await self.db_accessor.get_skills(record.agent_id, record.org_id)
                for skill in skills:
                    if skill.get("name") == record.skill_name:
                        await self.db_accessor.update_skill(
                            str(skill.get("skill_id", "")),
                            {"enabled": False, "deprecated": True},
                        )
                        break

            record.applied_at = datetime.utcnow().isoformat()
            return True

        except Exception:
            return False

    def get_evolution_history(self, agent_id: str | None = None) -> list[EvolutionRecord]:
        """获取进化历史。"""
        if agent_id:
            return [r for r in self._evolution_history if r.agent_id == agent_id]
        return list(self._evolution_history)

    # ---- 内部方法 ----

    async def _llm_analyze(
        self,
        agent_id: str,
        org_id: str,
        run_data: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        existing_skills: list[dict[str, Any]],
    ) -> RunAnalysis:
        """使用 LLM 分析运行历史。"""
        analysis = RunAnalysis(agent_id=agent_id)

        # 构建分析 Prompt
        run_data_summary = json.dumps(run_data[:20], ensure_ascii=False, indent=2)
        skills_summary = json.dumps(
            [{"name": s.get("name", ""), "description": s.get("description", "")} for s in existing_skills],
            ensure_ascii=False, indent=2,
        )

        prompt = ANALYZE_PROMPT.format(
            run_data=run_data_summary,
            existing_skills=skills_summary,
        )

        try:
            response_text = await self.llm_caller.call(
                prompt=prompt,
                system_prompt="你是一个 Agent 运行分析专家，擅长从运行历史中发现改进模式。",
                temperature=0.2,
            )

            result = self._parse_json_response(response_text)
            if result:
                analysis.success_rate = result.get("success_rate", 0.0)
                analysis.common_patterns = result.get("common_patterns", [])
                analysis.failure_patterns = result.get("failure_patterns", [])
                analysis.improvement_opportunities = result.get("improvement_opportunities", [])
        except Exception:
            # LLM 分析失败，降级到规则分析
            return self._rule_based_analyze(agent_id, run_data, messages, existing_skills)

        analysis.total_runs = len(run_data)
        return analysis

    def _rule_based_analyze(
        self,
        agent_id: str,
        run_data: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        existing_skills: list[dict[str, Any]],
    ) -> RunAnalysis:
        """基于规则的分析。"""
        analysis = RunAnalysis(agent_id=agent_id, total_runs=len(run_data))

        # 计算成功率
        if run_data:
            succeeded = len([r for r in run_data if r.get("status") == "succeeded"])
            analysis.success_rate = succeeded / len(run_data)

        # 识别常见用户意图
        intent_counts: dict[str, int] = {}
        for msg in messages:
            if msg.get("role") == "user":
                content = str(msg.get("content", "")).lower()
                # 简单关键词匹配
                for keyword in ["查找", "搜索", "创建", "生成", "分析", "总结", "翻译"]:
                    if keyword in content:
                        intent_counts[keyword] = intent_counts.get(keyword, 0) + 1

        for intent, count in sorted(intent_counts.items(), key=lambda x: -x[1])[:5]:
            analysis.common_patterns.append({
                "pattern": f"用户常使用'{intent}'类请求",
                "frequency": count,
                "type": "neutral",
            })

        # 如果有高频意图但没有对应 Skill，建议创建
        existing_skill_names = {s.get("name", "").lower() for s in existing_skills}
        for pattern in analysis.common_patterns:
            pattern_text = pattern.get("pattern", "")
            for keyword in ["查找", "搜索"]:
                if keyword in pattern_text and "search" not in existing_skill_names:
                    analysis.improvement_opportunities.append({
                        "type": "new_skill",
                        "description": f"创建知识搜索 Skill，用户频繁使用'{keyword}'类请求",
                        "affected_skill": f"{keyword}_skill",
                        "confidence": 0.6,
                        "reasoning": f"用户在 {pattern.get('frequency', 0)} 次请求中使用了'{keyword}'",
                    })

        return analysis

    def _bump_version(self, version: str) -> str:
        """递增版本号。"""
        try:
            parts = version.split(".")
            if len(parts) == 3:
                patch = int(parts[2]) + 1
                return f"{parts[0]}.{parts[1]}.{patch}"
            return "1.0.0"
        except (ValueError, IndexError):
            return "1.0.0"

    def _parse_json_response(self, text: str) -> dict[str, Any] | None:
        """解析 LLM 输出的 JSON。"""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    return None
            return None
