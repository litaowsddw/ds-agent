"""Model-aware, pre-request context token accounting.

Provider usage remains the source of truth for billing and cache hits after a
request completes. DeepSeek uses its official offline tokenizer; models without
an available tokenizer use the product's explicit characters/4 estimate.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
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


def preflight_chat_context(
    *,
    provider: str,
    model: str,
    compiled_prompt: str,
    components: Iterable[dict[str, object]],
) -> ContextTokenPreflight:
    """Count the exact outgoing DeepSeek chat payload before dispatch.

    The gateway sends one OpenAI-compatible ``user`` message whose content is
    ``compiled_prompt``.  Applying the official DeepSeek chat template to that
    exact message makes the total independent of character-count heuristics.
    """

    if not _supports_official_deepseek_tokenizer(provider, model):
        return _characters_per_four_preflight(compiled_prompt, components)

    try:
        tokenizer = _deepseek_tokenizer()
        messages = [{"role": "user", "content": compiled_prompt}]
        input_ids = tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
        )
        rendered = tokenizer.apply_chat_template(
            messages,
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

        content_start = rendered.find(compiled_prompt)
        if content_start < 0:
            return ContextTokenPreflight(
                input_tokens=len(input_ids),
                stable_prefix_tokens=None,
                status="official_total_only",
                tokenizer=DEEPSEEK_TOKENIZER_NAME,
                breakdown=[],
            )

        grouped = _count_component_tokens(
            offsets=offsets,
            content_start=content_start,
            components=components,
        )
        stable_boundary = compiled_prompt.find("[APPEND_ONLY_LOG]")
        stable_prefix_tokens = _count_stable_prefix_tokens(
            offsets=offsets,
            content_start=content_start,
            stable_boundary=stable_boundary,
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
        return _characters_per_four_preflight(compiled_prompt, components)


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
    content_start: int,
    components: Iterable[dict[str, object]],
) -> list[dict[str, object]]:
    spans = [
        {
            "key": str(component["key"]),
            "label": str(component["label"]),
            "start": content_start + int(component["start"]),
            "end": content_start + int(component["end"]),
        }
        for component in components
        if "start" in component and "end" in component
    ]
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
    return ordered


def _count_stable_prefix_tokens(
    *, offsets: list[tuple[int, int]], content_start: int, stable_boundary: int
) -> int | None:
    if stable_boundary < 0:
        return None
    boundary = content_start + stable_boundary
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
        if "start" not in component or "end" not in component:
            continue
        start = int(component["start"])
        end = int(component["end"])
        characters = max(0, end - start)
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
    stable_boundary = compiled_prompt.find("[APPEND_ONLY_LOG]")
    stable_prefix_tokens = (
        max(0, stable_boundary // 4) if stable_boundary >= 0 else None
    )
    return ContextTokenPreflight(
        input_tokens=total_tokens,
        stable_prefix_tokens=stable_prefix_tokens,
        status="characters_divided_by_4",
        tokenizer=None,
        breakdown=breakdown,
    )
