"""JSON-serializable payloads for streaming LLM usage events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.services.context_tokens import ContextTokenPreflight, count_stream_output_tokens
from app.services.metering import NormalizedUsage


@dataclass(slots=True)
class StreamUsageReporter:
    """Build local estimates and provider-final usage payloads for one LLM call."""

    provider: str
    model: str
    preflight: ContextTokenPreflight
    usage_scope: Literal["chat", "skill_create", "workflow"]
    usage_key: str
    token_limit: int
    workflow_node_id: str | None = None
    _text: list[str] = field(default_factory=list)

    def preflight_event(self) -> dict[str, object]:
        return self._base(
            usage_phase="preflight",
            input_tokens=self.preflight.input_tokens,
            output_tokens=0,
            context_tokens=self.preflight.input_tokens,
            token_limit=self.token_limit,
            tokenizer_status=self.preflight.status,
            tokenizer=self.preflight.tokenizer,
            stable_prefix_tokens=self.preflight.stable_prefix_tokens,
            prompt_breakdown=self.preflight.breakdown,
        )

    def append_text(self, text: str) -> dict[str, object]:
        self._text.append(text)
        output_tokens = count_stream_output_tokens(
            provider=self.provider,
            model=self.model,
            text="".join(self._text),
        )
        return self._base(
            usage_phase="estimated",
            input_tokens=self.preflight.input_tokens,
            output_tokens=output_tokens,
            context_tokens=(
                self.preflight.input_tokens + output_tokens
                if self.preflight.input_tokens is not None
                else None
            ),
            token_limit=self.token_limit,
            output_token_status=(
                "official_tokenizer"
                if self.preflight.status == "official_tokenizer"
                else "characters_divided_by_4"
            ),
        )

    def final_event(self, usage: NormalizedUsage) -> dict[str, object]:
        if usage.usage_status != "provider_final":
            return self.unavailable_final_event()
        return self._base(
            usage_phase="provider_final",
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            context_tokens=(
                usage.input_tokens + usage.output_tokens
                if usage.input_tokens is not None and usage.output_tokens is not None
                else None
            ),
            cache_read_input_tokens=usage.cache_read_input_tokens,
            usage_status=usage.usage_status,
            output_token_status=(
                "provider_final" if usage.output_tokens is not None else "unavailable"
            ),
            token_limit=self.token_limit,
            preflight_input_tokens=self.preflight.input_tokens,
            stable_prefix_tokens=self.preflight.stable_prefix_tokens,
            tokenizer_status=self.preflight.status,
            tokenizer=self.preflight.tokenizer,
            prompt_breakdown=self.preflight.breakdown,
        )

    def unavailable_final_event(self) -> dict[str, object]:
        return self._base(
            usage_phase="unavailable",
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            context_tokens=None,
            cache_read_input_tokens=None,
            usage_status="unavailable",
            output_token_status="unavailable",
            token_limit=self.token_limit,
            preflight_input_tokens=self.preflight.input_tokens,
            stable_prefix_tokens=self.preflight.stable_prefix_tokens,
            tokenizer_status=self.preflight.status,
            tokenizer=self.preflight.tokenizer,
            prompt_breakdown=self.preflight.breakdown,
        )

    def _base(self, *, usage_phase: str, **payload: object) -> dict[str, object]:
        event = {
            "usage_scope": self.usage_scope,
            "usage_key": self.usage_key,
            "usage_phase": usage_phase,
        }
        if self.workflow_node_id is not None:
            event["workflow_node_id"] = self.workflow_node_id
        event.update(payload)
        return event
