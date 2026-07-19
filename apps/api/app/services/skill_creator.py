"""Skill Creator helpers for chat-triggered skill generation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_PINYIN_MAP = {
    "会": "hui",
    "议": "yi",
    "总": "zong",
    "结": "jie",
}


@dataclass(slots=True)
class SkillIntent:
    is_skill_request: bool
    topic: str = ""


_SKILL_OBJECT = r"(?:skill|技能)"
_CONSULTATION_PREFIX = re.compile(r"^(?:请)?\s*(?:解释|介绍|说明|如何|怎么|能否|是否)", re.IGNORECASE)
_CHINESE_CREATE = re.compile(
    rf"^(?:请|帮我|请帮我)?\s*(?:创建|生成|新建)\s*(?:一个)?\s*{_SKILL_OBJECT}\s*(?:[:：]|用于|用来|关于)?\s*(?P<topic>.+)$",
    re.IGNORECASE,
)
_CHINESE_SUFFIX_CREATE = re.compile(
    rf"^(?:请|帮我|请帮我)?\s*(?:创建|生成|新建)\s*(?:一个)?\s*(?:用于|用来|关于)?\s*(?P<topic>.+?)\s*(?:的)?\s*{_SKILL_OBJECT}$",
    re.IGNORECASE,
)
_ENGLISH_CREATE = re.compile(
    r"^(?:please\s+)?(?:create|generate|new)\s+(?:a\s+)?skill\s+(?:for|about)?\s*(?P<topic>.+)$",
    re.IGNORECASE,
)


def detect_skill_creation_request(message: str) -> SkillIntent:
    """Detect whether a user is asking the Agent to create a new skill."""

    normalized = message.strip()
    if not normalized or _CONSULTATION_PREFIX.search(normalized):
        return SkillIntent(is_skill_request=False)
    match = (
        _CHINESE_CREATE.match(normalized)
        or _CHINESE_SUFFIX_CREATE.match(normalized)
        or _ENGLISH_CREATE.match(normalized)
    )
    if match is None:
        return SkillIntent(is_skill_request=False)
    topic = match.group("topic").strip(" ：:-")
    return SkillIntent(is_skill_request=bool(topic), topic=topic)


def extract_skill_markdown(text: str) -> str:
    """Extract a SKILL.md document from an LLM response."""

    stripped = text.strip()
    fenced = re.search(r"```(?:markdown|md)?\s*(?P<body>.*?)```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        stripped = fenced.group("body").strip()

    start = stripped.find("---")
    if start > 0:
        stripped = stripped[start:].strip()

    if not stripped.startswith("---"):
        raise ValueError("Generated skill is missing YAML frontmatter")
    second = stripped.find("---", 3)
    if second < 0:
        raise ValueError("Generated skill frontmatter is not closed")
    if "name:" not in stripped[:second] or "description:" not in stripped[:second]:
        raise ValueError("Generated skill frontmatter must include name and description")
    return stripped


def build_skill_directory(root: Path, skill_name: str) -> Path:
    """Return a safe local directory for a generated skill."""

    return root / _slugify(skill_name)


def write_skill_file(root: Path, skill_name: str, markdown: str) -> Path:
    """Write a generated SKILL.md under the local user skill directory."""

    directory = build_skill_directory(root, skill_name)
    directory.mkdir(parents=True, exist_ok=True)
    skill_path = directory / "SKILL.md"
    skill_path.write_text(markdown, encoding="utf-8")
    return skill_path


def _slugify(value: str) -> str:
    pieces: list[str] = []
    for char in value.lower():
        if char.isascii() and char.isalnum():
            pieces.append(char)
        elif char in _PINYIN_MAP:
            pieces.extend(["-", _PINYIN_MAP[char], "-"])
        else:
            pieces.append("-")
    slug = "".join(pieces)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "generated-skill"
