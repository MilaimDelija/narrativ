"""
NARRATIV API — FastAPI backend
================================
Endpoints:
  GET  /                      health check
  POST /analyze               raw CIB engine report
  POST /dashboard             CIB + dashboard payload
  POST /full                  complete pipeline (all four modules)
  GET  /demo                  pre-computed demo run
  GET  /reports               list stored reports
  GET  /reports/{id}          retrieve stored report
  GET  /reports/{id}/anchor   anchor proof for report
  POST /prebunk               generate prebunking for stored report
"""
from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import asyncpg
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Engine path
sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))

from coordination_engine import Account, CoordinationEngine, EngineConfig, Post
from dashboard_export import export_for_dashboard
from narrative_tracker import NarrativeTracker
from prebunking_engine import PrebunkingEngine
from blockchain_anchor import BlockchainAnchor
from database import (
    get_pool, init_schema,
    save_report, get_report, list_reports,
    save_anchor, save_prebunk_cards,
)
from middleware import RateLimitMiddleware
from logger import RequestLogMiddleware, log


# ── App lifecycle ─────────────────────────────────────────────────────────

_pool: Optional[asyncpg.Pool] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        try:
            _pool = await get_pool()
            await init_schema(_pool)
            log.info("Database connected and schema initialized")
        except Exception as exc:
            log.warning(f"DB init failed — running without persistence: {exc}")
    else:
        log.info("DATABASE_URL not set — running without persistence")
    yield
    if _pool:
        await _pool.close()
        log.info("Database pool closed")


app = FastAPI(
    title="NARRATIV API",
    description="Open infrastructure for influence operation detection",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Middleware (order matters: outermost first)
app.add_middleware(RequestLogMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# ── Pydantic models ───────────────────────────────────────────────────────

class PostIn(BaseModel):
    post_id: str
    account_id: str
    timestamp: str
    text: str
    hashtags: list[str] = []
    amplifies_account: Optional[str] = None
    is_sponsored: bool = False

class AccountIn(BaseModel):
    account_id: str
    created_at: str
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

class PrebunkRequest(BaseModel):
    report_id: str
    languages: list[str] = ["sq", "en", "de"]
    atom_id: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────

def _parse_dt(s: str):
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

def _follower_map(accounts: list[AccountIn]) -> dict[str, int]:
    return {a.account_id: a.followers for a in accounts}

def _require_posts(posts: list) -> None:
    if not posts:
        raise HTTPException(status_code=422, detail="posts list is empty")

def _require_db() -> asyncpg.Pool:
    if not _pool:
        raise HTTPException(status_code=503,
            detail="Database not configured — set DATABASE_URL")
    return _pool


# ── Routes ────────────────────────────────────────────────────────────────

@app.get("/", tags=["health"])
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "NARRATIV API",
        "version": "2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "db_connected": _pool is not None,
        "modules": ["cib_detector", "narrative_tracker",
                    "prebunking_engine", "blockchain_anchor"],
    }


@app.post("/analyze", tags=["analysis"])
def analyze(req: AnalyzeRequest) -> dict[str, Any]:
    """Raw CIB engine report."""
    _require_posts(req.posts)
    posts    = [_to_post(p) for p in req.posts]
    accounts = [_to_account(a) for a in req.accounts]
    cfg = EngineConfig(
        tlp=req.tlp,
        review_threshold=req.review_threshold,
        min_active_signals=req.min_active_signals,
    )
    return CoordinationEngine(config=cfg).analyze(posts, accounts)


@app.post("/dashboard", tags=["analysis"])
def dashboard(req: AnalyzeRequest) -> dict[str, Any]:
    """CIB engine + dashboard-ready payload."""
    _require_posts(req.posts)
    posts    = [_to_post(p) for p in req.posts]
    accounts = [_to_account(a) for a in req.accounts]
    cfg = EngineConfig(
        tlp=req.tlp,
        review_threshold=req.review_threshold,
        min_active_signals=req.min_active_signals,
    )
    report = CoordinationEngine(config=cfg).analyze(posts, accounts)
    return export_for_dashboard(report, posts, accounts, topic=req.topic)


@app.post("/full", tags=["analysis"])
async def full_analysis(req: AnalyzeRequest) -> dict[str, Any]:
    """
    Complete pipeline:
    1. CIB detection
    2. Narrative tracking
    3. Dashboard export
    4. Prebunking generation
    5. Blockchain anchoring
    6. Persist to DB (if configured)
    """
    _require_posts(req.posts)
    log.info(f"Full analysis: topic={req.topic} posts={len(req.posts)} accounts={len(req.accounts)}")

    posts    = [_to_post(p) for p in req.posts]
    accounts = [_to_account(a) for a in req.accounts]
    fm       = _follower_map(req.accounts)

    # 1. CIB
    cfg = EngineConfig(
        tlp=req.tlp,
        review_threshold=req.review_threshold,
        min_active_signals=req.min_active_signals,
    )
    cib_report = CoordinationEngine(config=cfg).analyze(posts, accounts)
    log.info(f"CIB done: flagged={cib_report['summary']['flagged_for_review']}")

    # 2. Narrative Tracker
    tracker_report = NarrativeTracker().track(posts, follower_map=fm)
    log.info(f"Tracker done: atoms={tracker_report['narrative_atoms_detected']}")

    # 3. Dashboard export
    dashboard_data = export_for_dashboard(cib_report, posts, accounts, topic=req.topic)

    # 4. Prebunking
    prebunk_report = PrebunkingEngine().generate(cib_report, tracker_report)
    log.info(f"Prebunking done: cards={prebunk_report['total_cards']}")

    # 5. Blockchain anchor
    proof = BlockchainAnchor().anchor({**cib_report, "topic": req.topic})
    log.info(f"Anchor: on_chain={proof.on_chain} hash={proof.report_hash[:18]}…")

    # 6. Persist
    if _pool:
        try:
            await save_report(_pool, proof.report_id, req.topic, req.tlp,
                               cib_report, tracker_report, dashboard_data)
            await save_anchor(_pool, proof.as_dict())
            await save_prebunk_cards(_pool, proof.report_id, prebunk_report["cards"])
        except Exception as exc:
            log.warning(f"DB persist error: {exc}")

    return {
        "report_id":        proof.report_id,
        "cib":              cib_report,
        "narrative_tracker": tracker_report,
        "dashboard":        dashboard_data,
        "prebunking":       prebunk_report,
        "anchor":           proof.as_dict(),
    }


@app.get("/demo", tags=["demo"])
def demo_run() -> dict[str, Any]:
    """Pre-computed demo run (no input required)."""
    path = Path(__file__).parent.parent / "engine" / "dashboard_data.json"
    if not path.exists():
        raise HTTPException(404, "demo data not found — run engine/demo.py first")
    return json.loads(path.read_text())


@app.get("/reports", tags=["reports"])
async def list_stored_reports(
    limit: int = Query(20, ge=1, le=100),
    topic: Optional[str] = Query(None),
) -> list[dict]:
    pool = _require_db()
    return await list_reports(pool, limit=limit, topic=topic)


@app.get("/reports/{report_id}", tags=["reports"])
async def get_stored_report(report_id: str) -> dict[str, Any]:
    pool = _require_db()
    row = await get_report(pool, report_id)
    if not row:
        raise HTTPException(404, f"Report '{report_id}' not found")
    return row


@app.post("/prebunk", tags=["prebunking"])
async def generate_prebunk(req: PrebunkRequest) -> dict[str, Any]:
    """Generate prebunking cards for a stored report."""
    pool = _require_db()
    row = await get_report(pool, req.report_id)
    if not row:
        raise HTTPException(404, f"Report '{req.report_id}' not found")
    cib     = row.get("cib_report", {}) or {}
    tracker = row.get("tracker_report", {}) or {}
    result  = PrebunkingEngine(languages=req.languages).generate(
        cib, tracker, atom_id=req.atom_id)
    await save_prebunk_cards(pool, req.report_id, result["cards"])
    return result
