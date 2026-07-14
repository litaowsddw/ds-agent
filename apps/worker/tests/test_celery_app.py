"""Local Celery adapter behaviour tests."""

from apps.worker.app.celery_app import LocalCelery


def test_local_celery_bound_task_injects_task_adapter() -> None:
    """The fallback must mirror Celery's ``bind=True`` task calling convention."""

    app = LocalCelery()

    @app.task(name="test.bound", bind=True, max_retries=2)
    def bound_task(task, value: str) -> dict[str, str]:
        return {"task_name": task.name, "value": value}

    @app.task(name="test.unbound")
    def unbound_task(value: str) -> str:
        return value.upper()

    assert bound_task.run("value") == {"task_name": "test.bound", "value": "value"}
    assert bound_task.delay("queued").value == {
        "task_name": "test.bound",
        "value": "queued",
    }
    assert unbound_task.run("value") == "VALUE"


def test_local_celery_apply_async_unpacks_task_arguments() -> None:
    """The fallback accepts Celery's args/kwargs scheduling shape."""

    app = LocalCelery()

    @app.task(name="test.bound", bind=True)
    def bound_task(task, value: str, *, suffix: str) -> str:
        return f"{task.name}:{value}{suffix}"

    @app.task(name="test.unbound")
    def unbound_task(value: str, *, suffix: str) -> str:
        return f"{value}{suffix}"

    assert bound_task.apply_async(
        args=("bound",), kwargs={"suffix": "!"}, countdown=5
    ).value == "test.bound:bound!"
    assert unbound_task.apply_async(
        args=("unbound",), kwargs={"suffix": "?"}, countdown=5
    ).value == "unbound?"
