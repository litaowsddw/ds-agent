"""SkillStore 测试。"""

import pytest

from apps.api.app.domain.skill import SkillScope
from apps.api.app.services.agent_store import AgentStore
from apps.api.app.services.identity_store import IdentityStore
from apps.api.app.services.skill_store import SkillStore

SKILL_CONTENT = """---
name: workflow-helper
description: 帮助用户设计和检查工作流。
---

# Instructions

当用户需要设计工作流时使用该 Skill。
"""


def test_skill_can_be_registered_and_allowed_for_agent() -> None:
    """有权限用户可以注册 Skill 并授权给 Agent。"""

    identity = IdentityStore()
    agent_store = AgentStore(identity=identity)
    skill_store = SkillStore(identity=identity, agents=agent_store)

    owner = identity.register_user("skill-owner@example.com", "Owner", "password123")
    organization = identity.create_organization(owner.user_id, "Skill 组织")
    agent = agent_store.create_agent(owner.user_id, organization.org_id, "Skill Agent", "")

    skill = skill_store.register_skill(
        actor_user_id=owner.user_id,
        org_id=organization.org_id,
        scope=SkillScope.ORGANIZATION,
        content=SKILL_CONTENT,
    )
    skill_store.set_agent_skill_policy(owner.user_id, agent.agent_id, skill.skill_id, True)

    summaries = skill_store.list_allowed_skill_summaries(owner.user_id, agent.agent_id)

    assert summaries[0]["name"] == "workflow-helper"
    assert "帮助用户设计" in summaries[0]["description"]


def test_unallowed_skill_content_is_rejected() -> None:
    """未授权 Skill 不能被 Agent 读取完整内容。"""

    identity = IdentityStore()
    agent_store = AgentStore(identity=identity)
    skill_store = SkillStore(identity=identity, agents=agent_store)

    owner = identity.register_user("skill-block@example.com", "Owner", "password123")
    organization = identity.create_organization(owner.user_id, "Skill Block 组织")
    agent = agent_store.create_agent(owner.user_id, organization.org_id, "Skill Block Agent", "")
    skill = skill_store.register_skill(
        owner.user_id, organization.org_id, SkillScope.ORGANIZATION, SKILL_CONTENT
    )

    with pytest.raises(PermissionError):
        skill_store.get_skill_content(owner.user_id, agent.agent_id, skill.skill_id)
