"""
Database layer — Neon PostgreSQL
=================================
Schema and async helpers for storing CIB reports, narrative tracker
outputs, anchor proofs, and campaign history.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL", "")


async def get_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)


# ── Schema ────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id            SERIAL PRIMARY KEY,
    report_id     TEXT UNIQUE NOT NULL,
    topic         TEXT,
    tlp           TEXT DEFAULT 'TLP:AMBER',
    cib_report    JSONB,
    tracker_report JSONB,
    dashboard_data JSONB,
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS anchor_proofs (
    id            SERIAL PRIMARY KEY,
    report_id     TEXT NOT NULL REFERENCES reports(report_id),
    report_hash   TEXT NOT NULL,
    on_chain      BOOLEAN DEFAULT FALSE,
    tx_hash       TEXT,
    block_number  INTEGER,
    network       TEXT DEFAULT 'polygon_amoy',
    anchored_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS prebunk_cards (
    id            SERIAL PRIMARY KEY,
    report_id     TEXT REFERENCES reports(report_id),
    atom_id       TEXT,
    technique     TEXT,
    language      TEXT,
    headline      TEXT,
    explanation   TEXT,
    warning_signs JSONB,
    verification_guide TEXT,
    generated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reports_created ON reports(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reports_topic   ON reports(topic);
CREATE INDEX IF NOT EXISTS idx_anchors_report  ON anchor_proofs(report_id);
"""


async def init_schema(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA)


# ── Reports ───────────────────────────────────────────────────────────────

async def save_report(pool: asyncpg.Pool, report_id: str, topic: str,
                       tlp: str, cib_report: dict, tracker_report: dict,
                       dashboard_data: dict) -> None:
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO reports (report_id, topic, tlp, cib_report, tracker_report, dashboard_data)
            VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb)
            ON CONFLICT (report_id) DO UPDATE
            SET cib_report=$4::jsonb, tracker_report=$5::jsonb,
                dashboard_data=$6::jsonb
        """, report_id, topic, tlp,
            json.dumps(cib_report),
            json.dumps(tracker_report),
            json.dumps(dashboard_data))


async def get_report(pool: asyncpg.Pool, report_id: str) -> Optional[dict]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM reports WHERE report_id=$1", report_id)
        if not row:
            return None
        return dict(row)


async def list_reports(pool: asyncpg.Pool, limit: int = 20,
                        topic: Optional[str] = None) -> list[dict]:
    async with pool.acquire() as conn:
        if topic:
            rows = await conn.fetch(
                "SELECT report_id, topic, tlp, created_at FROM reports "
                "WHERE topic ILIKE $1 ORDER BY created_at DESC LIMIT $2",
                f"%{topic}%", limit)
        else:
            rows = await conn.fetch(
                "SELECT report_id, topic, tlp, created_at FROM reports "
                "ORDER BY created_at DESC LIMIT $1", limit)
        return [dict(r) for r in rows]


# ── Anchor proofs ─────────────────────────────────────────────────────────

async def save_anchor(pool: asyncpg.Pool, proof: dict) -> None:
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO anchor_proofs
              (report_id, report_hash, on_chain, tx_hash, block_number, network)
            VALUES ($1,$2,$3,$4,$5,$6)
        """, proof["report_id"], proof["report_hash"], proof["on_chain"],
            proof.get("tx_hash"), proof.get("block_number"), proof["network"])


# ── Prebunk cards ─────────────────────────────────────────────────────────

async def save_prebunk_cards(pool: asyncpg.Pool,
                              report_id: str, cards: list[dict]) -> None:
    async with pool.acquire() as conn:
        await conn.executemany("""
            INSERT INTO prebunk_cards
              (report_id, atom_id, technique, language, headline,
               explanation, warning_signs, verification_guide)
            VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8)
        """, [
            (report_id, c.get("source_atom_id"), c["technique"],
             c["language"], c["headline"], c["explanation"],
             json.dumps(c["warning_signs"]), c["verification_guide"])
            for c in cards
        ])
