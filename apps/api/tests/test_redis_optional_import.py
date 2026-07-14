"""Regression coverage for importing the Redis helper without redis installed."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_redis_helper_imports_without_redis_site_package() -> None:
    """Optional Redis support must not prevent unrelated API modules importing."""
    api_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            "from app.core import redis; assert redis.Redis is None; assert redis.ConnectionPool is None",
        ],
        cwd=api_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
