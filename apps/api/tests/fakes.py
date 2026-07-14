"""Test-only LLM doubles for Gateway and synchronous workflow-store tests."""

from typing import Any

from apps.api.app.gateway.llm import LLMCallRequest, LLMCallResponse


class FakeLLMProvider:
    """Deterministic provider that exercises the real asynchronous Gateway API."""

    def generate(self, request: LLMCallRequest) -> LLMCallResponse:
        return LLMCallResponse(
            text="[fake-llm] response",
            provider=request.provider,
            model=request.model,
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            raw={},
        )


class FakeWorkflowGateway:
    """Synchronous workflow callback used only by WorkflowRunStore unit tests."""

    def generate_from_workflow_node(
        self, config: dict[str, Any], node_input: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "text": "[fake-llm] workflow response",
            "provider": str(config.get("provider") or "mock"),
            "model": str(config.get("model") or "mock-model"),
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "prefix_hash": "test-prefix-hash",
            "upstream": node_input.get("upstream", {}),
        }
