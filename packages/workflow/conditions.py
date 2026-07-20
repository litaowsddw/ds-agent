"""Data-only condition parsing and evaluation for Workflow branches.

Condition nodes intentionally expose a deliberately small language.  They can
only test whether a resolved value exists or equals a JSON scalar.  This keeps
workflow routing deterministic and avoids evaluating user supplied Python,
JavaScript, or expression strings in the API process.
"""

from __future__ import annotations

import ast
import json
import math
import re
from dataclasses import dataclass
from typing import Any

from packages.workflow.templates import WorkflowTemplateError, collect_template_references


_EXACT_REFERENCE = re.compile(r"^\s*{{\s*([^{}]+?)\s*}}\s*$")
_LEGACY_EQUALS = re.compile(r"^\s*(\{\{\s*[^{}]+?\s*}})\s*==\s*(.+?)\s*$")
_LEGACY_EXISTS = re.compile(r"^\s*(?:exists\(\s*)?(\{\{\s*[^{}]+?\s*}})\s*\)?\s*$")
_OPERATORS = frozenset({"equals", "exists"})


class WorkflowConditionError(ValueError):
    """Raised when a condition configuration is outside the supported DSL."""


@dataclass(frozen=True, slots=True)
class WorkflowCondition:
    """A parsed data-only condition ready for validation or execution."""

    left: str
    operator: str
    value: Any = None
    has_value: bool = False


def normalize_condition_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return a modern condition config, accepting the old strict UI syntax.

    The canvas shipped before executable conditions used an ``expression``
    text field.  We accept only its safe subset (``{{input.flag}}`` for
    existence and ``{{input.status}} == 'approved'`` for equality), translate
    it to the explicit schema, and reject everything else.  No expression is
    ever passed to ``eval`` or an interpreter.
    """

    condition = parse_condition_config(config)
    normalized = dict(config)
    normalized.update(
        {
            "left": condition.left,
            "operator": condition.operator,
        }
    )
    if condition.has_value:
        normalized["value"] = condition.value
    else:
        normalized.pop("value", None)
    return normalized


def parse_condition_config(config: dict[str, Any]) -> WorkflowCondition:
    """Parse an explicit or legacy-safe condition config without evaluating it."""

    has_explicit = any(key in config for key in ("left", "field", "operator", "value"))
    if has_explicit:
        if "expression" in config and str(config.get("expression") or "").strip():
            raise WorkflowConditionError("条件节点不能同时配置 expression 和 left/operator")
        left = config.get("left", config.get("field"))
        operator = config.get("operator")
        if not isinstance(left, str) or not left.strip():
            raise WorkflowConditionError("条件节点必须配置 left 字段引用")
        if not isinstance(operator, str) or operator not in _OPERATORS:
            raise WorkflowConditionError("条件节点 operator 只能是 equals 或 exists")
        has_value = "value" in config
        value = config.get("value")
        if operator == "equals" and not has_value:
            raise WorkflowConditionError("equals 条件必须配置 value")
        if operator == "exists" and has_value:
            raise WorkflowConditionError("exists 条件不能配置 value")
        if has_value:
            _validate_literal(value)
        _validate_left_reference(left)
        return WorkflowCondition(left=left, operator=operator, value=value, has_value=has_value)

    expression = config.get("expression")
    if not isinstance(expression, str) or not expression.strip():
        raise WorkflowConditionError("条件节点必须配置 left/operator，或安全的 expression")

    equals_match = _LEGACY_EQUALS.fullmatch(expression)
    if equals_match:
        left = equals_match.group(1)
        value = _parse_expression_literal(equals_match.group(2))
        _validate_left_reference(left)
        return WorkflowCondition(left=left, operator="equals", value=value, has_value=True)

    exists_match = _LEGACY_EXISTS.fullmatch(expression)
    if exists_match:
        left = exists_match.group(1)
        _validate_left_reference(left)
        return WorkflowCondition(left=left, operator="exists")

    raise WorkflowConditionError(
        "条件 expression 仅支持 {{input.field}}、"
        "{{input.field}} == 'value' 或 exists({{upstream.node.field}})"
    )


def evaluate_condition(config: dict[str, Any]) -> bool:
    """Evaluate a normalized condition whose ``left`` value is already resolved."""

    operator = config.get("operator")
    if operator == "exists":
        return _value_exists(config.get("left"))
    if operator == "equals":
        left = config.get("left")
        value = config.get("value")
        # JSON boolean and numeric values are distinct.  ``True == 1`` is a
        # Python convenience, not a workflow author's expected branch rule.
        return type(left) is type(value) and left == value
    raise WorkflowConditionError("条件节点 operator 只能是 equals 或 exists")


def _validate_left_reference(left: str) -> None:
    match = _EXACT_REFERENCE.fullmatch(left)
    if match is None:
        raise WorkflowConditionError("条件 left 必须是单个变量引用，例如 {{input.status}}")
    try:
        references = collect_template_references(left)
    except WorkflowTemplateError as exc:
        raise WorkflowConditionError(str(exc)) from exc
    if len(references) != 1:
        raise WorkflowConditionError("条件 left 必须是单个变量引用")


def _parse_expression_literal(raw_value: str) -> Any:
    """Parse only a JSON/Python scalar literal from the legacy equality form."""

    candidate = raw_value.strip()
    if not candidate:
        raise WorkflowConditionError("条件 equals 右侧不能为空")
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        try:
            value = ast.literal_eval(candidate)
        except (SyntaxError, ValueError) as exc:
            raise WorkflowConditionError(
                "条件 equals 右侧必须是字符串、数字、true/false 或 null 字面量"
            ) from exc
    _validate_literal(value)
    return value


def _validate_literal(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise WorkflowConditionError("条件 value 不能是 NaN 或 Infinity")
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    raise WorkflowConditionError("条件 value 只能是字符串、数字、布尔值或 null")


def _value_exists(value: Any) -> bool:
    """Define existence explicitly so empty input does not become a truthiness trap."""

    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True
