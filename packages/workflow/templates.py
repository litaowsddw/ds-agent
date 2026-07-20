"""Safe variable interpolation for Workflow node configuration.

Workflow authors can reference the run input with ``{{input.customer_id}}``
and a previously executed node output with ``{{retrieve.chunks.0.content}}``.
This module intentionally implements a small data-only language: no Python
attributes, function calls, filters, or expressions are evaluated.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

_PATH_SEGMENT = re.compile(r"^[A-Za-z0-9_-]+$")
_SPECIAL_ROOTS = frozenset({"input", "workflow_input", "upstream"})


class WorkflowTemplateError(ValueError):
    """Raised when a Workflow template is malformed or cannot be resolved."""


@dataclass(frozen=True, slots=True)
class TemplateReference:
    """One parsed ``{{namespace.path}}`` reference."""

    expression: str
    parts: tuple[str, ...]

    @property
    def root(self) -> str:
        return self.parts[0]


def collect_template_references(template: str) -> list[TemplateReference]:
    """Parse all template references and reject unsupported syntax eagerly."""

    references: list[TemplateReference] = []
    position = 0
    while position < len(template):
        opening = template.find("{{", position)
        closing = template.find("}}", position)
        if closing >= 0 and (opening < 0 or closing < opening):
            raise WorkflowTemplateError("模板占位符存在没有对应 '{{' 的 '}}'")
        if opening < 0:
            break
        end = template.find("}}", opening + 2)
        if end < 0:
            fragment = template[opening:]
            raise WorkflowTemplateError(f"模板占位符未闭合：{fragment}")

        expression = template[opening + 2 : end].strip()
        if not expression:
            raise WorkflowTemplateError("模板占位符不能为空")
        parts = tuple(part.strip() for part in expression.split("."))
        if any(not part or not _PATH_SEGMENT.fullmatch(part) for part in parts):
            raise WorkflowTemplateError(
                f"模板占位符 '{{{{{expression}}}}}' 不合法；仅支持 input.field 或 node_id.field"
            )
        if any(part.startswith("_") for part in parts):
            raise WorkflowTemplateError(
                f"模板占位符 '{{{{{expression}}}}}' 不允许访问以下划线开头的字段"
            )
        references.append(TemplateReference(expression=expression, parts=parts))
        position = end + 2

    return references


def resolve_template_value(
    value: Any,
    *,
    variables: Mapping[str, Any],
    location: str,
) -> Any:
    """Recursively render config data using only values in ``variables``.

    A string containing exactly one reference keeps the referenced native type.
    This is essential for Tool JSON arguments such as ``{"docs":
    "{{retrieve.chunks}}"}``. Mixed text is rendered as a string with objects
    encoded as deterministic JSON.
    """

    if isinstance(value, str):
        return _render_string(value, variables=variables, location=location)
    if isinstance(value, list):
        return [
            resolve_template_value(item, variables=variables, location=f"{location}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, Mapping):
        return {
            key: resolve_template_value(item, variables=variables, location=f"{location}.{key}")
            for key, item in value.items()
        }
    return deepcopy(value)


def _render_string(template: str, *, variables: Mapping[str, Any], location: str) -> Any:
    references = collect_template_references(template)
    if not references:
        return template

    matches = list(re.finditer(r"{{\s*([^{}]+?)\s*}}", template))
    if len(matches) != len(references):  # Defensive guard for future parser changes.
        raise WorkflowTemplateError(f"{location} 包含无法解析的模板占位符")

    resolved_values = [
        _resolve_reference(reference, variables=variables, location=location)
        for reference in references
    ]
    only_reference = len(matches) == 1 and matches[0].span() == (0, len(template))
    if only_reference:
        return deepcopy(resolved_values[0])

    rendered_parts: list[str] = []
    position = 0
    for match, resolved in zip(matches, resolved_values, strict=True):
        rendered_parts.append(template[position : match.start()])
        rendered_parts.append(_stringify(resolved))
        position = match.end()
    rendered_parts.append(template[position:])
    rendered = "".join(rendered_parts)
    if "{{" in rendered or "}}" in rendered:
        raise WorkflowTemplateError(
            f"{location} 渲染后仍包含模板占位符；请不要把未解析变量作为变量值传递"
        )
    return rendered


def _resolve_reference(
    reference: TemplateReference,
    *,
    variables: Mapping[str, Any],
    location: str,
) -> Any:
    root = reference.root
    if root not in variables:
        raise WorkflowTemplateError(
            f"{location} 引用了 '{{{{{reference.expression}}}}}'，"
            f"但变量 '{root}' 不存在或不是已连接的上游节点输出"
        )

    value: Any = variables[root]
    for part in reference.parts[1:]:
        if isinstance(value, Mapping):
            if part not in value:
                raise WorkflowTemplateError(
                    f"{location} 引用了 '{{{{{reference.expression}}}}}'，"
                    f"但字段 '{part}' 不存在"
                )
            value = value[part]
        elif isinstance(value, list):
            if not part.isdigit():
                raise WorkflowTemplateError(
                    f"{location} 引用了 '{{{{{reference.expression}}}}}'，"
                    f"列表字段必须使用数字下标，当前为 '{part}'"
                )
            index = int(part)
            if index >= len(value):
                raise WorkflowTemplateError(
                    f"{location} 引用了 '{{{{{reference.expression}}}}}'，"
                    f"列表下标 {index} 超出范围"
                )
            value = value[index]
        else:
            raise WorkflowTemplateError(
                f"{location} 引用了 '{{{{{reference.expression}}}}}'，"
                f"但字段 '{part}' 的上级值不是对象或列表"
            )
    return value


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def is_special_root(root: str) -> bool:
    """Return whether ``root`` is a built-in variable namespace."""

    return root in _SPECIAL_ROOTS
