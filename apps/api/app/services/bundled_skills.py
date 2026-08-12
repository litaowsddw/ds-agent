"""平台内置 Skill（opencode 默认 Skill 思路）。

`app/assets/skills/<name>/SKILL.md` 随代码分发，对所有组织默认可用，
不需要落库。加载结果带进程内缓存；测试可用 ``list_bundled_skills.cache_clear``
重置。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_BUNDLED_SKILLS_DIR = Path(__file__).resolve().parents[1] / "assets" / "skills"
_FRONTMATTER_PATTERN = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass(frozen=True, slots=True)
class BundledSkill:
    """磁盘内置 Skill，满足 skill_disclosure 的 SkillLike 结构协议。"""

    skill_id: str
    name: str
    description: str
    content: str
    file_path: str | None
    scope: str = "bundled"


def _parse_frontmatter(content: str) -> dict[str, str]:
    match = _FRONTMATTER_PATTERN.match(content)
    if not match:
        return {}
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


@lru_cache(maxsize=1)
def list_bundled_skills() -> tuple[BundledSkill, ...]:
    """扫描 assets/skills 目录，返回全部内置 Skill（按名称排序）。"""
    if not _BUNDLED_SKILLS_DIR.is_dir():
        return ()

    skills: list[BundledSkill] = []
    for skill_dir in sorted(_BUNDLED_SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            continue
        content = skill_file.read_text(encoding="utf-8")
        meta = _parse_frontmatter(content)
        name = meta.get("name") or skill_dir.name
        skills.append(
            BundledSkill(
                skill_id=f"bdl_{name}",
                name=name,
                description=meta.get("description", ""),
                content=content,
                file_path=str(skill_file),
            )
        )
    return tuple(skills)
