"""结构化日志配置。

提供统一的 JSON 格式日志和请求上下文注入：
- JSON 结构化输出（生产环境）
- 人类可读格式（开发环境）
- 请求 ID 追踪
- 用户上下文自动注入
- 日志级别控制
"""

import json
import logging
import os
import sys
import time
from contextvars import ContextVar
from typing import Any


# ──────────────────────────────────────
# 请求上下文
# ──────────────────────────────────────

# 请求级上下文变量
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")
org_id_var: ContextVar[str] = ContextVar("org_id", default="")
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


def set_request_context(
    request_id: str = "",
    user_id: str = "",
    org_id: str = "",
    trace_id: str = "",
) -> None:
    """设置当前请求上下文。"""
    if request_id:
        request_id_var.set(request_id)
    if user_id:
        user_id_var.set(user_id)
    if org_id:
        org_id_var.set(org_id)
    if trace_id:
        trace_id_var.set(trace_id)


def clear_request_context() -> None:
    """清除当前请求上下文。"""
    request_id_var.set("")
    user_id_var.set("")
    org_id_var.set("")
    trace_id_var.set("")


# ──────────────────────────────────────
# JSON 格式化器
# ──────────────────────────────────────

_LOG_FORMAT = os.getenv("LOG_FORMAT", "json" if os.getenv("PRODUCTION") else "console")
_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


class JSONFormatter(logging.Formatter):
    """JSON 结构化日志格式化器。"""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # 注入请求上下文
        request_id = request_id_var.get("")
        if request_id:
            log_data["request_id"] = request_id

        user_id = user_id_var.get("")
        if user_id:
            log_data["user_id"] = user_id

        org_id = org_id_var.get("")
        if org_id:
            log_data["org_id"] = org_id

        trace_id = trace_id_var.get("")
        if trace_id:
            log_data["trace_id"] = trace_id

        # 异常信息
        if record.exc_info and record.exc_info[0] is not None:
            log_data["exception"] = self.formatException(record.exc_info)

        # 附加字段
        if hasattr(record, "extra_data"):
            log_data["data"] = record.extra_data

        return json.dumps(log_data, ensure_ascii=False, default=str)


class ConsoleFormatter(logging.Formatter):
    """开发环境人类可读格式化器。"""

    COLORS = {
        "DEBUG": "\033[36m",     # 青色
        "INFO": "\033[32m",      # 绿色
        "WARNING": "\033[33m",   # 黄色
        "ERROR": "\033[31m",     # 红色
        "CRITICAL": "\033[35m",  # 紫色
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        # 颜色
        color = self.COLORS.get(record.levelname, "")
        reset = self.RESET if color else ""

        # 请求上下文
        ctx_parts = []
        request_id = request_id_var.get("")
        user_id = user_id_var.get("")
        if request_id:
            ctx_parts.append(f"req={request_id[:8]}")
        if user_id:
            ctx_parts.append(f"user={user_id[:8]}")
        ctx_str = f" [{', '.join(ctx_parts)}]" if ctx_parts else ""

        # 基本格式
        timestamp = self.formatTime(record, "%H:%M:%S")
        message = record.getMessage()

        result = f"{color}{timestamp} {record.levelname:8s}{reset}{ctx_str} {record.name}: {message}"

        # 异常信息
        if record.exc_info and record.exc_info[0] is not None:
            result += "\n" + self.formatException(record.exc_info)

        return result


# ──────────────────────────────────────
# 日志配置
# ──────────────────────────────────────

def setup_logging() -> None:
    """配置全局日志。"""
    root_logger = logging.getLogger()

    # 避免重复配置
    if root_logger.handlers:
        return

    # 日志级别
    level = getattr(logging, _LOG_LEVEL, logging.INFO)
    root_logger.setLevel(level)

    # 控制台处理器
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    # 格式化器
    if _LOG_FORMAT == "json":
        formatter = JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
    else:
        formatter = ConsoleFormatter(datefmt="%H:%M:%S")

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # 降低第三方库日志级别
    for name in ("uvicorn", "uvicorn.access", "sqlalchemy", "httpx", "httpcore", "celery"):
        logging.getLogger(name).setLevel(logging.WARNING)

    root_logger.info("日志系统初始化完成", extra={"extra_data": {"format": _LOG_FORMAT, "level": _LOG_LEVEL}})


# ──────────────────────────────────────
# FastAPI 请求日志中间件
# ──────────────────────────────────────

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from uuid import uuid4


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件。

    为每个请求：
    1. 生成 request_id
    2. 注入用户上下文
    3. 记录请求开始/结束
    4. 记录请求耗时
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 跳过噪音路径
        if request.url.path in ("/health", "/health/", "/metrics", "/docs", "/openapi.json"):
            return await call_next(request)

        # 生成 request_id
        req_id = request.headers.get("X-Request-Id", uuid4().hex[:16])
        set_request_context(request_id=req_id)

        # 提取用户上下文
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            from app.core.security import verify_access_token
            payload = verify_access_token(auth_header[7:])
            if payload:
                set_request_context(user_id=payload.user_id, org_id=payload.org_id or "")

        logger = logging.getLogger("agentflow.request")
        start_time = time.time()

        logger.info(
            f"→ {request.method} {request.url.path}",
            extra={"extra_data": {
                "method": request.method,
                "path": str(request.url.path),
                "query": str(request.query_params) if request.query_params else "",
                "client_ip": request.client.host if request.client else "",
            }},
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            duration = time.time() - start_time
            from app.core.metrics import record_api_request

            record_api_request(request.method, request.url.path, 500, duration)
            logger.error(
                f"✗ {request.method} {request.url.path} - 500 ({duration*1000:.0f}ms) - {exc}",
                extra={"extra_data": {"duration_ms": duration * 1000, "error": str(exc)}},
                exc_info=True,
            )
            raise

        duration = time.time() - start_time
        from app.core.metrics import record_api_request

        record_api_request(request.method, request.url.path, response.status_code, duration)

        # 注入追踪头
        response.headers["X-Request-Id"] = req_id
        trace_id = trace_id_var.get("")
        if trace_id:
            response.headers["X-Trace-Id"] = trace_id

        level = logging.WARNING if response.status_code >= 400 else logging.INFO
        logger.log(
            level,
            f"← {request.method} {request.url.path} - {response.status_code} ({duration*1000:.0f}ms)",
            extra={"extra_data": {
                "method": request.method,
                "path": str(request.url.path),
                "status_code": response.status_code,
                "duration_ms": duration * 1000,
            }},
        )

        # 清除请求上下文
        clear_request_context()

        return response
