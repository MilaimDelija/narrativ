"""
Rate limiting and request logging middleware.
Uses Upstash Redis (REST API) — no persistent connection needed.
Falls back to in-memory counter if Redis is not configured.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import Callable

import httpx
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


# ── Redis client (Upstash REST) ───────────────────────────────────────────

REDIS_URL   = os.getenv("UPSTASH_REDIS_REST_URL", "")
REDIS_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")

async def _redis_incr_ex(key: str, ttl: int) -> int:
    """INCR + EXPIRE via Upstash REST. Returns new counter value."""
    headers = {"Authorization": f"Bearer {REDIS_TOKEN}"}
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{REDIS_URL}/incr/{key}", headers=headers, timeout=2.0)
        count = r.json().get("result", 1)
        if count == 1:
            await client.get(f"{REDIS_URL}/expire/{key}/{ttl}", headers=headers, timeout=2.0)
    return count


# ── In-memory fallback ────────────────────────────────────────────────────

_mem_counts: dict[str, list] = defaultdict(lambda: [0, 0.0])  # [count, window_start]

def _mem_incr(key: str, ttl: int) -> int:
    now = time.time()
    entry = _mem_counts[key]
    if now - entry[1] > ttl:
        entry[0] = 0
        entry[1] = now
    entry[0] += 1
    return entry[0]


# ── Rate limit config ─────────────────────────────────────────────────────

LIMITS: dict[str, tuple[int, int]] = {
    # path_prefix: (max_requests, window_seconds)
    "/full":     (20,  60),   # expensive — 20 req/min per IP
    "/analyze":  (60,  60),
    "/dashboard":(60,  60),
    "/demo":     (120, 60),
    "/reports":  (120, 60),
    "/prebunk":  (30,  60),
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Find applicable limit
        limit, window = None, None
        for prefix, (lim, win) in LIMITS.items():
            if request.url.path.startswith(prefix):
                limit, window = lim, win
                break

        if limit is None:
            return await call_next(request)

        # Client identifier
        forwarded = request.headers.get("x-forwarded-for", "")
        ip = forwarded.split(",")[0].strip() if forwarded else (
            request.client.host if request.client else "unknown")
        key = f"rl:{ip}:{request.url.path}"

        try:
            if REDIS_URL and REDIS_TOKEN:
                count = await _redis_incr_ex(key, window)
            else:
                count = _mem_incr(key, window)
        except Exception:
            count = 0  # fail open — don't block on Redis errors

        if count > limit:
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded: {limit} req/{window}s"},
                headers={"Retry-After": str(window)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - count))
        return response
