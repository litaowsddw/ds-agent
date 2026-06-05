from pathlib import Path

from apps.api.app.gateway.llm import OpenAICompatibleProvider
from apps.api.app.services.chat_events import ChatTraceEvent, format_sse_event
from apps.api.app.services.skill_creator import (
    build_skill_directory,
    detect_skill_creation_request,
    extract_skill_markdown,
)


def test_formats_sse_event_with_json_payload() -> None:
    event = ChatTraceEvent(
        event="node_started",
        data={"node": "llm_call", "label": "Call DeepSeek"},
    )

    payload = format_sse_event(event)

    assert payload.startswith("event: node_started\n")
    assert '"node":"llm_call"' in payload
    assert payload.endswith("\n\n")


def test_detects_chinese_skill_creation_request() -> None:
    result = detect_skill_creation_request("帮我创建一个用于总结会议纪要的 skill")

    assert result.is_skill_request is True
    assert "总结会议纪要" in result.topic


def test_extract_skill_markdown_from_fenced_llm_output() -> None:
    markdown = extract_skill_markdown(
        """Here is the skill:

```markdown
---
name: meeting-summary
description: Summarize meeting notes into decisions and actions.
---

# Meeting Summary

## Steps
1. Read the notes.
```
"""
    )

    assert markdown.startswith("---\nname: meeting-summary")
    assert "# Meeting Summary" in markdown


def test_build_skill_directory_sanitizes_skill_name(tmp_path: Path) -> None:
    directory = build_skill_directory(tmp_path, "会议 总结/Skill")

    assert directory == tmp_path / "hui-yi-zong-jie-skill"


def test_extracts_openai_compatible_stream_delta() -> None:
    provider = OpenAICompatibleProvider(
        base_url="http://example.test",
        api_key="test-key",
        provider_key="deepseek",
    )

    assert provider._extract_stream_delta({"choices": [{"delta": {"content": "hello"}}]}) == "hello"
    assert provider._extract_stream_delta({"choices": [{"delta": {}}]}) == ""
