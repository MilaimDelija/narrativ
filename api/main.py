"""
NARRATIV API — FastAPI backend
Exposes the CIB engine over HTTP for the dashboard and external consumers.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Engine lives one level up in /engine — add to path when running from /api
sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))

from coordination_engine import Account, CoordinationEngine, EngineConfig, Post
from dashboard_export import export_for_dashboard

app = FastAPI(
    title="NARRATIV API",
    description="Open infrastructure for influence operation detection",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ─────────────────────────────────────────────

class PostIn(BaseModel):
    post_id: str
    account_id: str
    timestamp: str          # ISO-8601
    text: str
    hashtags: list[str] = []
    amplifies_account: str | None = None
    is_sponsored: bool = False


class AccountIn(BaseModel):
    account_id: str
    created_at: str         # ISO-8601
    followers: int
    following: int
    has_default_avatar: bool = False
    display_name: str = ""
    handle: str = ""


class AnalyzeRequest(BaseModel):
    posts: list[PostIn]
    accounts: list[AccountIn]
    topic: str = "#topic"
    tlp: str = "TLP:AMBER"
    review_threshold: float = 0.55
    min_active_signals: int = 2


# ── Helpers ───────────────────────────────────────────────────────────────

def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s).astimezone(timezone.utc)


def _to_post(p: PostIn) -> Post:
    post = Post(
        post_id=p.post_id,
        account_id=p.account_id,
        timestamp=_parse_dt(p.timestamp),
        text=p.text,
        hashtags=tuple(p.hashtags),
        amplifies_account=p.amplifies_account,
        is_sponsored=p.is_sponsored,
    )
    return post


def _to_account(a: AccountIn) -> Account:
    return Account(
        account_id=a.account_id,
        created_at=_parse_dt(a.created_at),
        followers=a.followers,
        following=a.following,
        has_default_avatar=a.has_default_avatar,
        display_name=a.display_name,
        handle=a.handle,
    )


# ── Routes ────────────────────────────────────────────────────────────────

@app.get("/")
def health():
    return {"status": "ok", "service": "NARRATIV API", "version": "1.0.0",
            "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/analyze")
def analyze(req: AnalyzeRequest) -> dict[str, Any]:
    """Run the CIB engine on a batch of posts and accounts."""
    if not req.posts:
        raise HTTPException(status_code=422, detail="posts list is empty")

    posts = [_to_post(p) for p in req.posts]
    accounts = [_to_account(a) for a in req.accounts]

    cfg = EngineConfig(
        tlp=req.tlp,
        review_threshold=req.review_threshold,
        min_active_signals=req.min_active_signals,
    )
    engine = CoordinationEngine(config=cfg)
    report = engine.analyze(posts, accounts)
    return report


@app.post("/dashboard")
def dashboard(req: AnalyzeRequest) -> dict[str, Any]:
    """Run the engine and return a dashboard-ready payload."""
    if not req.posts:
        raise HTTPException(status_code=422, detail="posts list is empty")

    posts = [_to_post(p) for p in req.posts]
    accounts = [_to_account(a) for a in req.accounts]

    cfg = EngineConfig(
        tlp=req.tlp,
        review_threshold=req.review_threshold,
        min_active_signals=req.min_active_signals,
    )
    engine = CoordinationEngine(config=cfg)
    report = engine.analyze(posts, accounts)
    payload = export_for_dashboard(report, posts, accounts, topic=req.topic)
    return payload


@app.get("/demo")
def demo_run() -> dict[str, Any]:
    """Return the pre-computed demo payload (no input needed)."""
    demo_path = Path(__file__).parent.parent / "engine" / "dashboard_data.json"
    if not demo_path.exists():
        raise HTTPException(status_code=404, detail="demo data not found — run engine/demo.py first")
    return json.loads(demo_path.read_text())
