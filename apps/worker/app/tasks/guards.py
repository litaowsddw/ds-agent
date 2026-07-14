"""Fail-closed guards for worker paths without trusted usage attribution."""


def async_worker_disabled_result() -> dict[str, str]:
    """Return the stable failure contract for disabled unmetered workers."""

    return {
        "status": "failed",
        "error_message": "Async supervisor worker execution is disabled until metered attribution is available.",
    }
