import json

from app.services.context_tokens import ContextTokenPreflight
from app.services.metering import normalize_usage
from app.services.stream_usage import StreamUsageReporter


def test_reporter_emits_preflight_progress_and_provider_final() -> None:
    reporter = StreamUsageReporter(
        provider="custom",
        model="unknown",
        preflight=ContextTokenPreflight(
            100, None, "characters_divided_by_4", None, []
        ),
        usage_scope="workflow",
        usage_key="run-1:llm-1",
        workflow_node_id="llm-1",
        token_limit=2400,
    )

    assert reporter.preflight_event()["usage_phase"] == "preflight"
    progress = reporter.append_text("x" * 40)
    assert progress["usage_phase"] == "estimated"
    assert progress["output_tokens"] == 10
    final = reporter.final_event(
        normalize_usage({"prompt_tokens": 120, "completion_tokens": 12})
    )
    assert final["usage_phase"] == "provider_final"
    assert final["input_tokens"] == 120
    assert final["workflow_node_id"] == "llm-1"


def test_reporter_marks_missing_provider_usage_unavailable_without_estimate() -> None:
    reporter = StreamUsageReporter(
        provider="custom",
        model="unknown",
        preflight=ContextTokenPreflight(
            100, None, "characters_divided_by_4", None, []
        ),
        usage_scope="chat",
        usage_key="chat-1",
        token_limit=2400,
    )
    reporter.append_text("x" * 40)

    final = reporter.final_event(normalize_usage(None))

    assert final["usage_phase"] == "unavailable"
    assert final["usage_status"] == "unavailable"
    assert final["input_tokens"] is None
    assert final["output_tokens"] is None
    assert final["context_tokens"] is None
    assert final["token_limit"] == 2400
    assert reporter.unavailable_final_event() == final
    json.dumps(final)
