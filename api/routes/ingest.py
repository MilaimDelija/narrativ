"""
Ingest routes — input layer for NARRATIV platform.

POST /ingest/upload     — CSV or JSON file upload → full analysis
POST /ingest/twitter    — fetch from Twitter/X API → full analysis
POST /ingest/telegram   — fetch from Telegram channels → full analysis
GET  /monitor           — list scheduled monitoring jobs
POST /monitor           — add a monitoring job
DELETE /monitor/{id}    — remove a monitoring job
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "engine"))

from coordination_engine import CoordinationEngine, EngineConfig, Post, Account
from narrative_tracker import NarrativeTracker
from prebunking_engine import PrebunkingEngine
from blockchain_anchor import BlockchainAnchor
from dashboard_export import export_for_dashboard
from connectors.base import ConnectorResult
from connectors.csv_import import CSVConnector
from connectors.twitter import TwitterConnector
from connectors.telegram import TelegramConnector
from connectors.scheduler import get_scheduler, MonitorJob

router = APIRouter()


def _run_pipeline(result: ConnectorResult, topic: str,
                   tlp: str = "TLP:AMBER") -> dict:
    if not result.posts:
        raise HTTPException(422, detail={
            "message": "No posts fetched",
            "errors": result.errors,
            "source": result.source,
        })
    fm = {a.account_id: a.followers for a in result.accounts}
    cfg     = EngineConfig(tlp=tlp)
    cib     = CoordinationEngine(config=cfg).analyze(result.posts, result.accounts)
    tracker = NarrativeTracker().track(result.posts, follower_map=fm)
    dash    = export_for_dashboard(cib, result.posts, result.accounts, topic=topic)
    prebunk = PrebunkingEngine().generate(cib, tracker)
    proof   = BlockchainAnchor().anchor({**cib, "topic": topic})
    return {
        "report_id":         proof.report_id,
        "source":            result.source,
        "fetched_at":        result.fetched_at.isoformat(),
        "total_fetched":     result.total_fetched,
        "connector_errors":  result.errors,
        "cib":               cib,
        "narrative_tracker": tracker,
        "dashboard":         dash,
        "prebunking":        prebunk,
        "anchor":            proof.as_dict(),
    }


@router.post("/ingest/upload", tags=["ingest"])
async def upload_file(
    file: UploadFile = File(...),
    topic: str = Form("#topic"),
    tlp: str = Form("TLP:AMBER"),
):
    content  = await file.read()
    filename = file.filename or ""

    if filename.endswith(".csv") or "csv" in (file.content_type or ""):
        result = CSVConnector().parse_string(
            content.decode("utf-8-sig", errors="replace"))

    elif filename.endswith(".json") or "json" in (file.content_type or ""):
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise HTTPException(422, f"Invalid JSON: {e}")

        if isinstance(data, list):
            posts = [Post(
                post_id=str(p.get("post_id", i)),
                account_id=str(p.get("account_id", "unknown")),
                timestamp=datetime.fromisoformat(
                    p.get("timestamp", "2024-01-01T00:00:00+00:00")),
                text=p.get("text", ""),
                hashtags=tuple(p.get("hashtags", [])),
                amplifies_account=p.get("amplifies_account"),
                is_sponsored=p.get("is_sponsored", False),
            ) for i, p in enumerate(data)]
            result = ConnectorResult(posts=posts, accounts=[],
                source="json_upload", fetched_at=datetime.now(timezone.utc),
                total_fetched=len(posts), errors=[])
        else:
            posts = [Post(
                post_id=p["post_id"], account_id=p["account_id"],
                timestamp=datetime.fromisoformat(p["timestamp"]),
                text=p["text"], hashtags=tuple(p.get("hashtags", [])),
                amplifies_account=p.get("amplifies_account"),
                is_sponsored=p.get("is_sponsored", False),
            ) for p in data.get("posts", [])]
            accounts = [Account(
                account_id=a["account_id"],
                created_at=datetime.fromisoformat(a["created_at"]),
                followers=a.get("followers", 0),
                following=a.get("following", 0),
                has_default_avatar=a.get("has_default_avatar", False),
                display_name=a.get("display_name", ""),
                handle=a.get("handle", ""),
            ) for a in data.get("accounts", [])]
            result = ConnectorResult(posts=posts, accounts=accounts,
                source="json_upload", fetched_at=datetime.now(timezone.utc),
                total_fetched=len(posts), errors=[])
    else:
        raise HTTPException(415, "Unsupported file type. Use .csv or .json")

    return _run_pipeline(result, topic=topic, tlp=tlp)


class TwitterRequest(BaseModel):
    query: str
    limit: int = 200
    topic: str = ""
    tlp: str = "TLP:AMBER"

@router.post("/ingest/twitter", tags=["ingest"])
def ingest_twitter(req: TwitterRequest):
    result = TwitterConnector().fetch(req.query, limit=req.limit)
    return _run_pipeline(result, topic=req.topic or req.query, tlp=req.tlp)


class TelegramRequest(BaseModel):
    channels: str
    limit: int = 200
    topic: str = ""
    tlp: str = "TLP:AMBER"

@router.post("/ingest/telegram", tags=["ingest"])
def ingest_telegram(req: TelegramRequest):
    result = TelegramConnector().fetch(req.channels, limit=req.limit)
    return _run_pipeline(result, topic=req.topic or req.channels, tlp=req.tlp)


class MonitorJobRequest(BaseModel):
    job_id: str
    connector: str
    query: str
    interval_minutes: int = 60
    notify_webhook: Optional[str] = None
    alert_threshold: float = 0.55

@router.get("/monitor", tags=["monitor"])
def list_monitor_jobs():
    s = get_scheduler()
    if not s:
        return {"jobs": [], "note": "apscheduler not installed"}
    return {"jobs": s.list_jobs()}

@router.post("/monitor", tags=["monitor"])
def add_monitor_job(req: MonitorJobRequest):
    s = get_scheduler()
    if not s:
        raise HTTPException(503, "apscheduler not installed")
    s.add_job(MonitorJob(
        job_id=req.job_id, connector_type=req.connector,
        query=req.query, interval_minutes=req.interval_minutes,
        notify_webhook=req.notify_webhook, alert_threshold=req.alert_threshold,
    ))
    return {"status": "added", "job_id": req.job_id}

@router.delete("/monitor/{job_id}", tags=["monitor"])
def remove_monitor_job(job_id: str):
    s = get_scheduler()
    if not s:
        raise HTTPException(503, "apscheduler not installed")
    s.remove_job(job_id)
    return {"status": "removed", "job_id": job_id}
