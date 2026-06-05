"""Progressive disclosure helpers for SKILL.md instructions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol


class SkillLike(Protocol):
    skill_id: str
    name: str
    description: str
    content: str
    file_path: str | None


@dataclass(frozen=True)
class SkillSelection:
    skill_id: str
    name: str
    reason: str


@dataclass(frozen=True)
class LoadedSkillContext:
    skill_id: str
    name: str
    reason: str
    content: str
    resources: list[tuple[str, str]]

    @property
    def prompt_context(self) -> str:
        blocks = [
            "A skill has been selected after checking the skill descriptions.",
            "Read and apply the selected SKILL.md workflow. Do not quote the skill unless the user asks.",
            f"Selected skill: {self.name}",
            f"Selection reason: {self.reason}",
            "[SKILL.md]",
            self.content,
        ]
        if self.resources:
            resource_blocks = []
            for relative_path, content in self.resources:
                resource_blocks.append(f"[Resource: {relative_path}]\n{content}")
            blocks.extend(["[Loaded Skill Resources]", "\n\n".join(resource_blocks)])
        return "\n\n".join(blocks)


def format_skill_description_catalog(skills: Iterable[SkillLike]) -> str:
    """Return only the name and description layer used by the skill router."""

    entries = []
    for skill in skills:
        description = str(skill.description or "").strip()
        entries.append(
            json.dumps(
                {
                    "skill_id": str(skill.skill_id),
                    "name": str(skill.name),
                    "description": description,
                },
                ensure_ascii=False,
            )
        )
    return "\n".join(entries)


def build_skill_router_prompt(message: str, catalog: str) -> str:
    return f"""Decide whether the user request should use one of the available skills.

Available skills are listed with description only. Do not infer hidden behavior from skill names.
Return strict JSON only:
{{"use_skill": true, "skill_id": "...", "reason": "..."}}
or
{{"use_skill": false, "skill_id": "", "reason": "..."}}

Use a skill only when its description clearly matches the user's task. If the user only greets, chats, or asks a general question, return use_skill false.

[Skill descriptions]
{catalog}

[User request]
{message}
"""


def parse_skill_selection(raw_response: str, skills: Iterable[SkillLike]) -> SkillSelection | None:
    skills_by_id = {str(skill.skill_id): skill for skill in skills}
    skills_by_name = {str(skill.name).lower(): skill for skill in skills}
    payload = _extract_json_object(raw_response)
    if not payload or not bool(payload.get("use_skill")):
        return None
    skill_id = str(payload.get("skill_id") or "").strip()
    skill = skills_by_id.get(skill_id)
    if skill is None:
        skill_name = str(payload.get("skill_name") or payload.get("name") or "").lower().strip()
        skill = skills_by_name.get(skill_name)
    if skill is None:
        return None
    return SkillSelection(
        skill_id=str(skill.skill_id),
        name=str(skill.name),
        reason=str(payload.get("reason") or "Matched by skill description."),
    )


def load_selected_skill_context(
    selection: SkillSelection,
    skills: Iterable[SkillLike],
    *,
    max_skill_chars: int = 12000,
    max_resource_chars: int = 4000,
    max_resources: int = 3,
) -> LoadedSkillContext | None:
    skill = next((item for item in skills if str(item.skill_id) == selection.skill_id), None)
    if skill is None:
        return None
    skill_content = _truncate(str(skill.content or ""), max_skill_chars)
    resources = load_referenced_resources(
        skill,
        max_resource_chars=max_resource_chars,
        max_resources=max_resources,
    )
    return LoadedSkillContext(
        skill_id=selection.skill_id,
        name=selection.name,
        reason=selection.reason,
        content=skill_content,
        resources=resources,
    )


def load_referenced_resources(
    skill: SkillLike,
    *,
    max_resource_chars: int = 4000,
    max_resources: int = 3,
) -> list[tuple[str, str]]:
    """Load small local resources explicitly referenced by the selected SKILL.md."""

    skill_path_raw = str(getattr(skill, "file_path", "") or "")
    if not skill_path_raw:
        return []
    skill_path = Path(skill_path_raw)
    if not skill_path.exists():
        return []
    skill_dir = skill_path.parent.resolve()
    resources: list[tuple[str, str]] = []
    for relative_path in _extract_resource_references(str(skill.content or "")):
        if len(resources) >= max_resources:
            break
        candidate = (skill_dir / relative_path).resolve()
        if not _is_inside(candidate, skill_dir) or not candidate.is_file():
            continue
        try:
            content = candidate.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        resources.append((relative_path, _truncate(content, max_resource_chars)))
    return resources


def _extract_json_object(text: str) -> dict[str, object] | None:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
    if fenced:
        stripped = fenced.group(1)
    elif "{" in stripped and "}" in stripped:
        stripped = stripped[stripped.find("{") : stripped.rfind("}") + 1]
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_resource_references(content: str) -> list[str]:
    candidates = re.findall(
        r"(?:resources|references|assets)/[A-Za-z0-9._/\-]+",
        content,
    )
    seen: set[str] = set()
    result: list[str] = []
    for candidate in candidates:
        normalized = candidate.replace("\\", "/").strip("/")
        if normalized in seen or ".." in normalized.split("/"):
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 24)].rstrip() + "\n[truncated]"
