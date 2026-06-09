# NARRATIV — Architecture

## Overview

```
[Data Sources] → [CIB Engine] → [FastAPI] → [Next.js Dashboard]
                      ↓
               [Blockchain Anchor]
               (Polygon Amoy)
```

## CIB Engine (engine/)

Four independent signal layers, combined score only flags when ≥ 2 layers fire:

| Layer | Method | Library |
|-------|--------|---------|
| Temporal | Co-firing window (60s buckets) | stdlib |
| Content | MinHash + LSH (threshold 0.7, 128 perm) | datasketch |
| Network | Louvain community detection | networkx |
| Metadata | Age burst, avatar, follower ratio | stdlib |

**Scoring weights:** temporal 30% · content 30% · network 25% · metadata 15%  
**Flag threshold:** combined ≥ 0.55 AND ≥ 2 active signals  
**Design principle:** under-flag preferred — a missed bot is recoverable, a false-flagged citizen is the exact harm this engine exists to avoid.

## API (api/)

FastAPI application, deployed on Render.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/analyze` | POST | Raw CIB engine report |
| `/dashboard` | POST | Dashboard-ready payload |
| `/demo` | GET | Pre-computed demo run |

## Frontend (frontend/)

Next.js 14 application, deployed on Vercel.  
Main component: `TransparencyDashboard` — consumes dashboard payload, renders stacked area chart with organic/coordinated/paid decomposition.

## Blockchain Anchoring

Evidence packets are anchored on Polygon Amoy (contract 0x1F04BCD4C6B97D201654F2Aa2a9F3cf91A35Ab33) via keccak256 hash of the report JSON. This makes documented campaigns tamper-evident.

## ATIP Integration

Engine output is directly compatible with ATIP surfaces:
- `report["graph"]` → Network Graph
- `report["clusters"]` → Campaign Tracker  
- `report["tlp"]` → TLP classification

## Deployment

- **API:** Render — `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Frontend:** Vercel — Next.js auto-detected
- **Database:** Neon PostgreSQL
- **Cache:** Upstash Redis
