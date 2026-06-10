"""
NARRATIV API — FastAPI backend (full)
======================================
Endpoints:
  GET  /                    health check
  POST /analyze             raw CIB engine report
  POST /dashboard           dashboard-ready payload
  POST /full                CIB + Narrative Tracker + Prebunking + Blockchain
  GET  /demo                pre-computed demo run
  GET  /reports             list stored reports
  GET  /reports/{id}        retrieve a stored report
  GET  /reports/{id}/anchor anchor proof for a report
  POST /prebunk             generate prebunking cards for a stored report
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
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Engine path
sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))

from coordination_engine import Account, CoordinationEngine, EngineConfig, Post
from dashboard_export import export_for_dashboard
from narrative_tracker import NarrativeTracker
from prebunking_engine import PrebunkingEngine
from blockchain_anchor import BlockchainAnchor
from database import (get_pool, init_schema, save_report, get_report,
                       list_reports, save_anchor, save_prebunk_cards)


# ── App lifecycle ─────────────────────────────────────────────────────────

_pool: Optional[asyncpg.Pool] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    if os.getenv("DATABASE_URL"):
        try:
            _pool = await get_pool()
            await init_schema(_pool)
        except Exception as e:
            print(f"DB init warning: {e} — running without persistence")
    yield
    if _pool:
        await _pool.close()


app = FastAPI(
    title="NARRATIV API",
    description="Open infrastructure for influence operation detection",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
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
    from datetime import timezone
    from datetime import datetime
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


# ── Routes ────────────────────────────────────────────────────────────────

@app.get("/")
def health():
    return {
        "status": "ok",
        "service": "NARRATIV API",
        "version": "2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "db_connected": _pool is not None,
    }


@app.post("/analyze")
def analyze(req: AnalyzeRequest) -> dict[str, Any]:
    """Raw CIB engine report."""
    if not req.posts:
        raise HTTPException(422, "posts list is empty")
    posts = [_to_post(p) for p in req.posts]
    accounts = [_to_account(a) for a in req.accounts]
    cfg = EngineConfig(tlp=req.tlp,
                        review_threshold=req.review_threshold,
                        min_active_signals=req.min_active_signals)
    return CoordinationEngine(config=cfg).analyze(posts, accounts)


@app.post("/dashboard")
def dashboard(req: AnalyzeRequest) -> dict[str, Any]:
    """CIB engine + dashboard-ready payload."""
    if not req.posts:
        raise HTTPException(422, "posts list is empty")
    posts = [_to_post(p) for p in req.posts]
    accounts = [_to_account(a) for a in req.accounts]
    cfg = EngineConfig(tlp=req.tlp,
                        review_threshold=req.review_threshold,
                        min_active_signals=req.min_active_signals)
    report = CoordinationEngine(config=cfg).analyze(posts, accounts)
    return export_for_dashboard(report, posts, accounts, topic=req.topic)


@app.post("/full")
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
    if not req.posts:
        raise HTTPException(422, "posts list is empty")

    posts    = [_to_post(p) for p in req.posts]
    accounts = [_to_account(a) for a in req.accounts]
    fm       = _follower_map(req.accounts)

    # 1. CIB
    cfg = EngineConfig(tlp=req.tlp,
                        review_threshold=req.review_threshold,
                        min_active_signals=req.min_active_signals)
    cib_report = CoordinationEngine(config=cfg).analyze(posts, accounts)

    # 2. Narrative Tracker
    tracker = NarrativeTracker()
    tracker_report = tracker.track(posts, follower_map=fm)

    # 3. Dashboard
    dashboard_data = export_for_dashboard(
        cib_report, posts, accounts, topic=req.topic)

    # 4. Prebunking
    prebunker = PrebunkingEngine()
    prebunk_report = prebunker.generate(cib_report, tracker_report)

    # 5. Blockchain anchor
    anchor = BlockchainAnchor()
    proof = anchor.anchor({**cib_report, "topic": req.topic})

    # 6. Persist
    report_id = proof.report_id
    if _pool:
        try:
            await save_report(_pool, report_id, req.topic, req.tlp,
                               cib_report, tracker_report, dashboard_data)
            await save_anchor(_pool, proof.as_dict())
            await save_prebunk_cards(_pool, report_id, prebunk_report["cards"])
        except Exception as e:
            print(f"DB persist warning: {e}")

    return {
        "report_id": report_id,
        "cib": cib_report,
        "narrative_tracker": tracker_report,
        "dashboard": dashboard_data,
        "prebunking": prebunk_report,
        "anchor": proof.as_dict(),
    }


@app.get("/demo")
def demo_run() -> dict[str, Any]:
    """Pre-computed demo payload."""
    demo_path = Path(__file__).parent.parent / "engine" / "dashboard_data.json"
    if not demo_path.exists():
        raise HTTPException(404, "demo data not found — run engine/demo.py first")
    return json.loads(demo_path.read_text())


@app.get("/reports")
async def list_stored_reports(limit: int = 20,
                               topic: Optional[str] = None) -> list[dict]:
    if not _pool:
        raise HTTPException(503, "database not configured")
    return await list_reports(_pool, limit=limit, topic=topic)


@app.get("/reports/{report_id}")
async def get_stored_report(report_id: str) -> dict[str, Any]:
    if not _pool:
        raise HTTPException(503, "database not configured")
    row = await get_report(_pool, report_id)
    if not row:
        raise HTTPException(404, f"report {report_id} not found")
    return row


@app.post("/prebunk")
async def generate_prebunk(req: PrebunkRequest) -> dict[str, Any]:
    """Generate prebunking cards for a stored report."""
    if not _pool:
        raise HTTPException(503, "database not configured")
    row = await get_report(_pool, req.report_id)
    if not row:
        raise HTTPException(404, f"report {req.report_id} not found")

    cib      = row.get("cib_report", {}) or {}
    tracker  = row.get("tracker_report", {}) or {}
    prebunker = PrebunkingEngine(languages=req.languages)
    result   = prebunker.generate(cib, tracker, atom_id=req.atom_id)

    await save_prebunk_cards(_pool, req.report_id, result["cards"])
    return result
