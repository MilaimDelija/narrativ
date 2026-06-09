"""
dashboard_export.py — the bridge between the CIB engine and the transparency
dashboard.

The engine reports *which accounts* show coordination signals. The dashboard
needs *reach over time, decomposed by source*. This module joins the two:
it classifies every post into one of three honest buckets and aggregates a
time series the dashboard can render directly.

Bucket rules (per post, first match wins):
  1. coordinated_review — author is in the engine's flagged_accounts
                          (a signal surfaced for human review, NOT a verdict)
  2. disclosed_paid     — post.is_sponsored is True (a confirmed, disclosed fact)
  3. organic            — everything else

Reach is an activity-weighted proxy: 1 + log1p(followers). No real reach API is
assumed; the axis is labelled honestly as an estimate so nothing is implied
that the data does not support.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone


def _reach_weight(followers: int) -> float:
    return 1.0 + math.log1p(max(0, followers))


def export_for_dashboard(report: dict, posts: list, accounts: list,
                         topic: str = "#topic", bucket_minutes: int = 10) -> dict:
    flagged = {a["account_id"] for a in report.get("flagged_accounts", [])}
    follower_of = {a.account_id: a.followers for a in accounts}

    def category(post) -> str:
        if post.account_id in flagged:
            return "coordinated"
        if getattr(post, "is_sponsored", False):
            return "paid"
        return "organic"

    if not posts:
        return {"topic": topic, "timeline": [], "totals": {}, "sources": [],
                "evidence": [], "clusters": []}

    t0 = min(p.timestamp for p in posts)
    span = bucket_minutes * 60

    buckets: dict[int, dict[str, float]] = defaultdict(
        lambda: {"organic": 0.0, "coordinated": 0.0, "paid": 0.0})
    for p in posts:
        slot = int((p.timestamp - t0).total_seconds() // span)
        w = _reach_weight(follower_of.get(p.account_id, 0))
        buckets[slot][category(p)] += w

    timeline = []
    for slot in sorted(buckets):
        ts = datetime.fromtimestamp(t0.timestamp() + slot * span, tz=timezone.utc)
        b = buckets[slot]
        timeline.append({
            "label": ts.strftime("%H:%M"),
            "minute": slot * bucket_minutes,
            "organic": round(b["organic"], 1),
            "coordinated": round(b["coordinated"], 1),
            "paid": round(b["paid"], 1),
        })

    totals = {k: round(sum(b[k] for b in buckets.values()), 1)
              for k in ("organic", "coordinated", "paid")}
    totals["all"] = round(sum(totals.values()), 1)

    # marker lines where coordinated waves peak (for the chart)
    coord_peaks = sorted(timeline, key=lambda r: r["coordinated"], reverse=True)
    markers = sorted({r["label"] for r in coord_peaks[:3] if r["coordinated"] > 0})

    evidence = _evidence_bullets(report)

    return {
        "topic": topic,
        "generated_at": report.get("generated_at", datetime.now(timezone.utc).isoformat()),
        "reach_unit": "activity-weighted estimate (1 + log followers)",
        "timeline": timeline,
        "totals": totals,
        "coordinated_markers": markers,
        "evidence": evidence,
        "clusters": report.get("clusters", []),
        "flagged_count": len(flagged),
        "tlp": report.get("tlp", "TLP:AMBER"),
    }


def _evidence_bullets(report: dict) -> list[str]:
    bullets: list[str] = []
    clusters = report.get("clusters", [])
    flagged = report.get("flagged_accounts", [])
    if flagged:
        bullets.append(f"{len(flagged)} accounts flagged across multiple independent signals.")
    for c in clusters[:2]:
        bullets.append(
            f"A pod of {c['size']} accounts with reciprocity {c['reciprocity']} "
            f"(closed mutual-amplification ring).")
    dup = report.get("summary", {}).get("cross_account_duplicate_pairs", 0)
    if dup:
        bullets.append(f"{dup} cross-account near-duplicate post pairs (shared copy).")
    if not bullets:
        bullets.append("No coordination signals cleared the review threshold.")
    return bullets


if __name__ == "__main__":
    # standalone: build the demo dataset, run the engine, export the JSON
    import demo  # noqa: F401  (running demo.py populates posts/accounts + report)

    payload = export_for_dashboard(
        demo.report, demo.posts, demo.accounts, topic="#protesta")
    with open("dashboard_data.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
