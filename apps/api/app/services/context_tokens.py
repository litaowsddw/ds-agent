"""Model-aware, pre-request context token accounting.

Provider usage remains the source of truth for billing and cache hits after a
request completes. DeepSeek uses its official offline tokenizer; models without
an available tokenizer use the product's explicit characters/4 estimate.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

DEEPSEEK_TOKENIZER_NAME = "deepseek-v3-official"


@dataclass(frozen=True)
class ContextTokenPreflight:
    """Pre-request context facts derived from a local official tokenizer."""

    input_tokens: int | None
    stable_prefix_tokens: int | None
    status: str
    tokenizer: str | None
    breakdown: list[dict[str, object]]


def count_stream_output_tokens(*, provider: str, model: str, text: str) -> int:
    """Count the assistant text accumulated so far during a stream.

    This is a live context-window indicator, not billable usage.  The final
    provider usage event remains authoritative because providers may include
    hidden/control tokens that are not observable in a streamed text delta.
    """

    if not text:
        return 0
    if _supports_official_deepseek_tokenizer(provider, model):
        try:
            token_ids = _deepseek_tokenizer()(text, add_special_tokens=False)["input_ids"]
            return len(token_ids)
        except Exception:
            pass
    return len(text) // 4


def preflight_chat_context(
    *,
    provider: str,
    model: str,
    compiled_prompt: str = "",
    components: Iterable[dict[str, object]],
    messages: list[dict[str, str]] | None = None,
) -> ContextTokenPreflight:
    """Count the exact outgoing provider message sequence before dispatch."""

    outgoing_messages = messages or [{"role": "user", "content": compiled_prompt}]
    fallback_text = compiled_prompt or _message_estimation_text(outgoing_messages)

    if not _supports_official_deepseek_tokenizer(provider, model):
        return _characters_per_four_preflight(fallback_text, components)

    try:
        tokenizer = _deepseek_tokenizer()
        input_ids = tokenizer.apply_chat_template(
            outgoing_messages,
            tokenize=True,
            add_generation_prompt=True,
        )
        rendered = tokenizer.apply_chat_template(
            outgoing_messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        encoded = tokenizer(
            rendered,
            add_special_tokens=False,
            return_offsets_mapping=True,
        )
        offsets = list(encoded.get("offset_mapping", []))
        encoded_ids = list(encoded.get("input_ids", []))
        # The template's direct token IDs are authoritative for the total.  If
        # offsets cannot faithfully reproduce them, expose the total only.
        if len(input_ids) != len(encoded_ids):
            return ContextTokenPreflight(
                input_tokens=len(input_ids),
                stable_prefix_tokens=None,
                status="official_total_only",
                tokenizer=DEEPSEEK_TOKENIZER_NAME,
                breakdown=[],
            )

        grouped, component_spans = _count_component_tokens(
            offsets=offsets,
            rendered=rendered,
            components=components,
        )
        stable_prefix_tokens = _count_stable_prefix_tokens(
            offsets=offsets,
            component_spans=component_spans,
        )
        return ContextTokenPreflight(
            input_tokens=len(input_ids),
            stable_prefix_tokens=stable_prefix_tokens,
            status="official_tokenizer",
            tokenizer=DEEPSEEK_TOKENIZER_NAME,
            breakdown=grouped,
        )
    except Exception:
        # A missing/corrupt optional tokenizer must not block the model request.
        return _characters_per_four_preflight(fallback_text, components)


def _supports_official_deepseek_tokenizer(provider: str, model: str) -> bool:
    normalized_provider = provider.lower().strip()
    normalized_model = model.lower().strip()
    return "deepseek" in normalized_provider or normalized_model.startswith("deepseek-")


@lru_cache(maxsize=1)
def _deepseek_tokenizer() -> Any:
    from transformers import AutoTokenizer

    assets = Path(__file__).resolve().parents[1] / "assets" / "deepseek_v3_tokenizer"
    return AutoTokenizer.from_pretrained(assets, local_files_only=True, trust_remote_code=False)


def _count_component_tokens(
    *,
    offsets: list[tuple[int, int]],
    rendered: str,
    components: Iterable[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Assign rendered chat-template tokens to the native message components."""

    component_list = list(components)
    spans: list[dict[str, object]] = []
    cursor = 0
    for component in component_list:
        content = str(component.get("content", ""))
        if not content:
            continue
        start = rendered.find(content, cursor)
        if start < 0:
            # Legacy single-prompt callers provide serialized spans.  Their
            # content is located after the full prompt starts in the template.
            if "start" not in component or "end" not in component:
                continue
            prompt_start = rendered.find(str(component.get("compiled_prompt", "")))
            if prompt_start < 0:
                continue
            start = prompt_start + int(component["start"])
            end = prompt_start + int(component["end"])
        else:
            end = start + len(content)
            cursor = end
        spans.append(
            {
                "key": str(component["key"]),
                "label": str(component["label"]),
                "start": start,
                "end": end,
                "stable_prefix": bool(component.get("stable_prefix", False)),
            }
        )
    counts: dict[str, dict[str, object]] = {}
    order: list[str] = []
    for span in spans:
        key = str(span["key"])
        if key not in counts:
            counts[key] = {"key": key, "label": span["label"], "tokens": 0}
            order.append(key)
    counts["protocol"] = {"key": "protocol", "label": "Prompt protocol / wrappers", "tokens": 0}

    for start, _ in offsets:
        owner = next((span for span in spans if span["start"] <= start < span["end"]), None)
        key = str(owner["key"]) if owner is not None else "protocol"
        counts[key]["tokens"] = int(counts[key]["tokens"]) + 1

    # Preserve assembly order and include protocol tokens (JSON punctuation,
    # wrappers and chat-template control tokens) as a separately inspectable
    # component instead of silently assigning them to user content.
    ordered = [counts[key] for key in order if int(counts[key]["tokens"]) > 0]
    if int(counts["protocol"]["tokens"]) > 0:
        ordered.append(counts["protocol"])
    return ordered, spans


def _count_stable_prefix_tokens(
    *, offsets: list[tuple[int, int]], component_spans: list[dict[str, object]]
) -> int | None:
    stable_ends = [int(span["end"]) for span in component_spans if span["stable_prefix"]]
    if not stable_ends:
        return None
    boundary = max(stable_ends)
    return sum(1 for start, _ in offsets if start < boundary)


def _characters_per_four_preflight(
    compiled_prompt: str, components: Iterable[dict[str, object]]
) -> ContextTokenPreflight:
    """Fallback the user explicitly chose for models without a tokenizer.

    It remains visually and semantically distinct from ``official_tokenizer``;
    it must never be used as a billable usage or an actual cache-hit value.
    """

    total_tokens = max(1, len(compiled_prompt) // 4)
    component_list = list(components)
    counts: dict[str, dict[str, object]] = {}
    order: list[str] = []
    for component in component_list:
        if "content" in component:
            characters = len(str(component["content"]))
        elif "start" in component and "end" in component:
            characters = max(0, int(component["end"]) - int(component["start"]))
        else:
            continue
        if characters:
            key = str(component["key"])
            if key not in counts:
                counts[key] = {"key": key, "label": str(component["label"]), "tokens": 0}
                order.append(key)
            counts[key]["tokens"] = int(counts[key]["tokens"]) + (
                characters * total_tokens
            ) // max(1, len(compiled_prompt))
    breakdown = [counts[key] for key in order]
    counted = sum(int(item["tokens"]) for item in breakdown)
    protocol_tokens = max(0, total_tokens - counted)
    if protocol_tokens:
        breakdown.append(
            {
                "key": "protocol",
                "label": "Prompt protocol / wrappers",
                "tokens": protocol_tokens,
            }
        )
    stable_characters = sum(
        len(str(component.get("content", "")))
        for component in component_list
        if bool(component.get("stable_prefix", False))
    )
    stable_prefix_tokens = max(0, stable_characters // 4) if stable_characters else None
    return ContextTokenPreflight(
        input_tokens=total_tokens,
        stable_prefix_tokens=stable_prefix_tokens,
        status="characters_divided_by_4",
        tokenizer=None,
        breakdown=breakdown,
    )


def _message_estimation_text(messages: list[dict[str, str]]) -> str:
    """Deterministic fallback representation when no model tokenizer exists."""

    return json.dumps(messages, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
