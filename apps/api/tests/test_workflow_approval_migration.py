"""Database-dialect regression checks for the workflow approval migration."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
from pathlib import Path

from alembic import op
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _load_approval_migration():
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260720_0005_add_workflow_approvals.py"
    )
    spec = spec_from_file_location("workflow_approval_migration", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_workflow_approval_migration_compiles_for_mysql_without_text_defaults() -> None:
    """MySQL does not permit ``DEFAULT`` values for TEXT in this migration."""

    stream = StringIO()
    context = MigrationContext.configure(
        dialect_name="mysql",
        opts={"as_sql": True, "output_buffer": stream},
    )
    previous_proxy = getattr(op, "_proxy", None)
    op._proxy = Operations(context)
    try:
        _load_approval_migration().upgrade()
    finally:
        if previous_proxy is None:
            del op._proxy
        else:
            op._proxy = previous_proxy

    ddl = stream.getvalue().upper()
    assert "ARGUMENTS_REDACTED TEXT NOT NULL" in ddl
    assert "ERROR_MESSAGE TEXT NOT NULL" in ddl
    assert "ARGUMENTS_REDACTED TEXT NOT NULL DEFAULT" not in ddl
    assert "ERROR_MESSAGE TEXT NOT NULL DEFAULT" not in ddl
