from types import SimpleNamespace

from apps.api.app.routes.chat import _build_agent_prompt
from apps.api.app.services.skill_disclosure import (
    build_skill_router_prompt,
    format_skill_description_catalog,
    load_selected_skill_context,
    parse_skill_selection,
)


def test_description_catalog_contains_only_description_layer() -> None:
    skills = [
        SimpleNamespace(
            skill_id="skl_api",
            name="api-error-log-reviewer",
            description="Review API error logs and summarize root causes.",
            content="## Workflow\n1. Inspect tracebacks.",
            file_path=None,
        )
    ]

    catalog = format_skill_description_catalog(skills)

    assert "api-error-log-reviewer" in catalog
    assert "Review API error logs" in catalog
    assert "Inspect tracebacks" not in catalog


def test_router_prompt_uses_skill_descriptions_not_skill_md() -> None:
    prompt = build_skill_router_prompt(
        "Analyze this IntegrityError log.",
        '{"skill_id":"skl_api","name":"api-error-log-reviewer","description":"Review API error logs."}',
    )

    assert "[Skill descriptions]" in prompt
    assert "Review API error logs" in prompt
    assert "[SKILL.md]" not in prompt


def test_parse_skill_selection_accepts_strict_json() -> None:
    skills = [
        SimpleNamespace(
            skill_id="skl_api",
            name="api-error-log-reviewer",
            description="Review API error logs.",
            content="",
            file_path=None,
        )
    ]

    selection = parse_skill_selection(
        '{"use_skill": true, "skill_id": "skl_api", "reason": "The request contains an API error log."}',
        skills,
    )

    assert selection is not None
    assert selection.skill_id == "skl_api"
    assert selection.name == "api-error-log-reviewer"


def test_load_selected_skill_context_loads_referenced_resources(tmp_path) -> None:
    skill_dir = tmp_path / "api-error-log-reviewer"
    resources_dir = skill_dir / "resources"
    resources_dir.mkdir(parents=True)
    (resources_dir / "root-causes.md").write_text("500 timeout means backend latency.", encoding="utf-8")
    skill_path = skill_dir / "SKILL.md"
    skill_content = """---
name: api-error-log-reviewer
description: Review API error logs.
---

## Workflow
1. Read resources/root-causes.md when root cause mapping is needed.
"""
    skill_path.write_text(skill_content, encoding="utf-8")
    skill = SimpleNamespace(
        skill_id="skl_api",
        name="api-error-log-reviewer",
        description="Review API error logs.",
        content=skill_content,
        file_path=str(skill_path),
    )
    selection = SimpleNamespace(
        skill_id="skl_api",
        name="api-error-log-reviewer",
        reason="Matched the API error log description.",
    )

    context = load_selected_skill_context(selection, [skill])

    assert context is not None
    assert "[SKILL.md]" in context.prompt_context
    assert "resources/root-causes.md" in context.prompt_context
    assert "backend latency" in context.prompt_context


def test_build_agent_prompt_keeps_catalog_and_loaded_skill_separate() -> None:
    agent = SimpleNamespace(
        name="test-agent",
        description="General assistant",
        system_prompt="Answer carefully.",
    )

    prompt = _build_agent_prompt(
        agent,
        "hello",
        skill_catalog='{"skill_id":"skl_api","description":"Review API logs."}',
        skill_context="Selected skill: api-error-log-reviewer\n[SKILL.md]\n## Workflow",
    )

    assert "[Available Skill Descriptions]" in prompt
    assert "[Loaded Skill]" in prompt
    assert "[SKILL.md]" in prompt
