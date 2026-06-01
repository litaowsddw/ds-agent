"""Skill 注册与授权服务。"""

import re

from apps.api.app.domain.identity import new_id
from apps.api.app.domain.skill import AgentSkillPolicy, Skill, SkillScope
from apps.api.app.services.agent_store import AgentStore, agent_store
from apps.api.app.services.identity_store import IdentityStore, identity_store
from apps.api.app.services.rbac import Permission
from apps.api.app.storage.local_state import local_state_store


class SkillStore:
    """管理 Skill 注册、解析和 Agent allowlist。"""

    def __init__(self, identity: IdentityStore, agents: AgentStore) -> None:
        # identity 用于组织权限校验。
        self.identity = identity

        # agents 用于读取 Agent 所属组织和群组。
        self.agents = agents

        # skills_by_id 保存 Skill 实体。
        self.skills_by_id: dict[str, Skill] = {}

        # policies_by_agent_skill 保存 Agent 对 Skill 的授权策略。
        self.policies_by_agent_skill: dict[str, AgentSkillPolicy] = {}
        self._load_state()

    def register_skill(
        self,
        actor_user_id: str,
        org_id: str,
        scope: SkillScope,
        content: str,
        team_id: str | None = None,
        agent_id: str | None = None,
    ) -> Skill:
        """注册 Skill。"""

        self.identity.assert_org_access(
            user_id=actor_user_id,
            org_id=org_id,
            permission=Permission.AGENT_CREATE,
        )

        if team_id is not None:
            self.identity._require_team_in_org(team_id=team_id, org_id=org_id)

        if agent_id is not None:
            agent = self.agents.get_agent(actor_user_id=actor_user_id, agent_id=agent_id)
            if agent.org_id != org_id:
                raise ValueError("Agent 不属于该组织")

        metadata = self.parse_skill_markdown(content)
        skill = Skill(
            skill_id=new_id("skl"),
            org_id=org_id,
            team_id=team_id,
            agent_id=agent_id,
            scope=scope,
            name=metadata["name"],
            description=metadata["description"],
            content=content,
            created_by=actor_user_id,
        )
        self.skills_by_id[skill.skill_id] = skill
        self._save_state()
        return skill

    def set_agent_skill_policy(
        self,
        actor_user_id: str,
        agent_id: str,
        skill_id: str,
        allowed: bool,
    ) -> AgentSkillPolicy:
        """设置 Agent 是否允许使用某个 Skill。"""

        agent = self.agents.get_agent(actor_user_id=actor_user_id, agent_id=agent_id)
        self.identity.assert_org_access(actor_user_id, agent.org_id, Permission.AGENT_CREATE)

        skill = self._require_skill(skill_id)
        if skill.org_id not in ("", agent.org_id):
            raise ValueError("Skill 不属于该 Agent 的组织")

        policy = AgentSkillPolicy(agent_id=agent_id, skill_id=skill_id, allowed=allowed)
        self.policies_by_agent_skill[self._policy_key(agent_id, skill_id)] = policy
        self._save_state()
        return policy

    def list_allowed_skill_summaries(
        self, actor_user_id: str, agent_id: str
    ) -> list[dict[str, str]]:
        """列出 Agent 可用 Skill 摘要。"""

        agent = self.agents.get_agent(actor_user_id=actor_user_id, agent_id=agent_id)

        visible_skills = [
            skill
            for skill in self.skills_by_id.values()
            if skill.enabled and self._skill_visible_to_agent(skill=skill, agent_id=agent.agent_id)
        ]

        # summaries 按 name 排序，保证上下文注入顺序稳定。
        summaries = [
            {
                "skill_id": skill.skill_id,
                "name": skill.name,
                "description": skill.description,
                "scope": skill.scope.value,
            }
            for skill in sorted(visible_skills, key=lambda item: item.name)
        ]
        return summaries

    def list_skills(self, actor_user_id: str, org_id: str) -> list[Skill]:
        """列出组织内可见的 Skill。"""

        self.identity.assert_org_access(actor_user_id, org_id, Permission.ORGANIZATION_READ)
        skills = [skill for skill in self.skills_by_id.values() if skill.org_id in ("", org_id)]
        return sorted(skills, key=lambda skill: skill.name)

    def get_skill_content(self, actor_user_id: str, agent_id: str, skill_id: str) -> Skill:
        """读取授权 Skill 的完整内容。"""

        self.agents.get_agent(actor_user_id=actor_user_id, agent_id=agent_id)
        skill = self._require_skill(skill_id)

        policy = self.policies_by_agent_skill.get(self._policy_key(agent_id, skill_id))
        if policy is None or not policy.allowed:
            raise PermissionError("Agent 未被授权使用该 Skill")

        return skill

    def parse_skill_markdown(self, content: str) -> dict[str, str]:
        """解析 SKILL.md 的 name 和 description。"""

        # frontmatter_match 用于读取 Markdown 文件顶部的 YAML 风格元数据。
        frontmatter_match = re.match(r"^---\n(?P<body>.*?)\n---", content, flags=re.DOTALL)
        if frontmatter_match is None:
            raise ValueError("SKILL.md 缺少 frontmatter")

        frontmatter = frontmatter_match.group("body")
        metadata: dict[str, str] = {}
        for line in frontmatter.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip().strip('"').strip("'")

        if not metadata.get("name"):
            raise ValueError("SKILL.md 缺少 name")
        if not metadata.get("description"):
            raise ValueError("SKILL.md 缺少 description")

        return {"name": metadata["name"], "description": metadata["description"]}

    def _skill_visible_to_agent(self, skill: Skill, agent_id: str) -> bool:
        """判断 Skill 是否对指定 Agent 可见且已授权。"""

        policy = self.policies_by_agent_skill.get(self._policy_key(agent_id, skill.skill_id))
        return policy is not None and policy.allowed

    def _require_skill(self, skill_id: str) -> Skill:
        """要求 Skill 必须存在。"""

        skill = self.skills_by_id.get(skill_id)
        if skill is None:
            raise ValueError("Skill 不存在")
        return skill

    def _policy_key(self, agent_id: str, skill_id: str) -> str:
        """生成 Agent-Skill 授权索引键。"""

        return f"{agent_id}:{skill_id}"

    def _load_state(self) -> None:
        """从本地状态文件恢复 Skill 与授权策略。"""

        state = local_state_store.load_bucket("skills", {})
        if not isinstance(state, dict):
            return
        self.skills_by_id = state.get("skills_by_id", self.skills_by_id)
        self.policies_by_agent_skill = state.get(
            "policies_by_agent_skill",
            self.policies_by_agent_skill,
        )

    def _save_state(self) -> None:
        """把 Skill 与授权策略保存到本地状态文件。"""

        local_state_store.save_bucket(
            "skills",
            {
                "skills_by_id": self.skills_by_id,
                "policies_by_agent_skill": self.policies_by_agent_skill,
            },
        )


# skill_store 是 MVP 阶段的进程内 Skill 注册表。
skill_store = SkillStore(identity=identity_store, agents=agent_store)
