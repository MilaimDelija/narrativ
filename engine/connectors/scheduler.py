"""
Scheduler — runs CIB analysis automatically at configured intervals.
Uses APScheduler (lightweight, no Redis needed for basic use).

Supports:
  - Recurring keyword/hashtag monitoring
  - Telegram channel monitoring
  - Webhook notification on detection above threshold

Config via environment or JSON config file.
"""
from __future__ import annotations

import json
import os
import httpx
from datetime import datetime, timezone
from typing import Optional

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    _APScheduler = True
except ImportError:
    _APScheduler = False

from coordination_engine import CoordinationEngine, EngineConfig
from narrative_tracker import NarrativeTracker
from prebunking_engine import PrebunkingEngine
from blockchain_anchor import BlockchainAnchor


class MonitorJob:
    def __init__(self, job_id: str, connector_type: str,
                 query: str, interval_minutes: int,
                 notify_webhook: Optional[str] = None,
                 alert_threshold: float = 0.55):
        self.job_id            = job_id
        self.connector_type    = connector_type
        self.query             = query
        self.interval_minutes  = interval_minutes
        self.notify_webhook    = notify_webhook
        self.alert_threshold   = alert_threshold
        self.last_run: Optional[datetime] = None
        self.last_report: Optional[dict]  = None


class NarrativScheduler:
    """
    Background scheduler for automated NARRATIV monitoring.
    """

    def __init__(self):
        if not _APScheduler:
            raise ImportError("apscheduler not installed — pip install apscheduler")
        self._scheduler = BackgroundScheduler(timezone="UTC")
        self._jobs: dict[str, MonitorJob] = {}

    def add_job(self, job: MonitorJob) -> None:
        self._jobs[job.job_id] = job
        self._scheduler.add_job(
            func=self._run_job,
            trigger=IntervalTrigger(minutes=job.interval_minutes),
            args=[job.job_id],
            id=job.job_id,
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc),
        )

    def remove_job(self, job_id: str) -> None:
        self._scheduler.remove_job(job_id)
        self._jobs.pop(job_id, None)

    def start(self) -> None:
        self._scheduler.start()

    def stop(self) -> None:
        self._scheduler.shutdown(wait=False)

    def list_jobs(self) -> list[dict]:
        return [
            {
                "job_id":           j.job_id,
                "connector":        j.connector_type,
                "query":            j.query,
                "interval_minutes": j.interval_minutes,
                "last_run":         j.last_run.isoformat() if j.last_run else None,
                "alert_threshold":  j.alert_threshold,
            }
            for j in self._jobs.values()
        ]

    def _run_job(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return

        result = self._fetch(job)
        if not result or not result.posts:
            return

        job.last_run = datetime.now(timezone.utc)

        cfg    = EngineConfig(review_threshold=job.alert_threshold)
        engine = CoordinationEngine(config=cfg)
        report = engine.analyze(result.posts, result.accounts)
        job.last_report = report

        flagged = report["summary"]["flagged_for_review"]
        if flagged > 0 and job.notify_webhook:
            self._notify(job, report, flagged)

    def _fetch(self, job: MonitorJob):
        try:
            if job.connector_type == "twitter":
                from connectors.twitter import TwitterConnector
                return TwitterConnector().fetch(job.query)
            elif job.connector_type == "telegram":
                from connectors.telegram import TelegramConnector
                return TelegramConnector().fetch(job.query)
            else:
                return None
        except Exception:
            return None

    def _notify(self, job: MonitorJob, report: dict, flagged: int) -> None:
        payload = {
            "job_id":  job.job_id,
            "query":   job.query,
            "flagged": flagged,
            "tlp":     report.get("tlp", "TLP:AMBER"),
            "ts":      datetime.now(timezone.utc).isoformat(),
            "summary": report.get("summary", {}),
        }
        try:
            with httpx.Client(timeout=5) as client:
                client.post(job.notify_webhook, json=payload)
        except Exception:
            pass


# Singleton — used by API
_scheduler_instance: Optional[NarrativScheduler] = None

def get_scheduler() -> Optional[NarrativScheduler]:
    global _scheduler_instance
    if _scheduler_instance is None and _APScheduler:
        _scheduler_instance = NarrativScheduler()
        _scheduler_instance.start()
    return _scheduler_instance
