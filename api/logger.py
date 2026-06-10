"""
Structured logging for the NARRATIV API.
JSON lines to stdout — compatible with Render log drains.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log = {
            "ts":      self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level":   record.levelname,
            "logger":  record.name,
            "msg":     record.getMessage(),
        }
        if record.exc_info:
            log["exc"] = self.formatException(record.exc_info)
        return json.dumps(log, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # Silence noisy libraries
    for name in ("uvicorn.access", "httpx", "asyncio"):
        logging.getLogger(name).setLevel(logging.WARNING)
    return logging.getLogger("narrativ")


log = setup_logging(level="INFO")


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        t0 = time.perf_counter()
        response = await call_next(request)
        ms = round((time.perf_counter() - t0) * 1000, 1)
        log.info(json.dumps({
            "method": request.method,
            "path":   request.url.path,
            "status": response.status_code,
            "ms":     ms,
            "ip":     (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                       or (request.client.host if request.client else "-")),
        }))
        return response
