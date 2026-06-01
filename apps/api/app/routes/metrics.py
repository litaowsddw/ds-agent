"""Prometheus 指标暴露端点。"""

from fastapi import APIRouter, Response

from app.core.metrics import get_prometheus_metrics

router = APIRouter()


@router.get("")
async def prometheus_metrics() -> Response:
    """Prometheus 指标端点（/metrics）。"""
    content = get_prometheus_metrics()
    return Response(
        content=content,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
