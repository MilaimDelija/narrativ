# NARRATIV — Architecture

## System Overview

```
[Data Sources]
      │
      ▼
[FastAPI /full endpoint]
      │
      ├─→ [CIB Detector]          coordination_engine.py
      │         │ flagged accounts, clusters, graph
      ├─→ [Narrative Tracker]     narrative_tracker.py
      │         │ atoms, provenance chains, spread velocity
      ├─→ [Dashboard Export]      dashboard_export.py
      │         │ organic / coordinated / paid time series
      ├─→ [Prebunking Engine]     prebunking_engine.py
      │         │ technique cards (sq / de / en)
      └─→ [Blockchain Anchor]     blockchain_anchor.py
                │ keccak256 hash → Polygon Amoy

[Neon PostgreSQL] ← persisted reports, cards, anchor proofs
[Upstash Redis]   ← rate limiting, queue

[Next.js Dashboard]
  ├── TransparencyDashboard  (organic/coordinated/paid chart)
  ├── NarrativeTracker       (provenance timeline + network graph)
  ├── PrebunkingPanel        (technique cards by language)
  └── AnchorView             (blockchain proof display)
```

## CIB Engine — Four Signal Layers

| Layer | Method | Library | Weight |
|-------|--------|---------|--------|
| Temporal | Co-firing window (60s buckets) | stdlib | 30% |
| Content | MinHash + LSH (threshold 0.7, 128 perm) | datasketch | 30% |
| Network | Louvain community detection | networkx | 25% |
| Metadata | Age burst, avatar, follower ratio | stdlib | 15% |

**Flag condition:** combined score ≥ 0.55 AND ≥ 2 independent signals active.  
**Accuracy (demo):** 12/12 bots caught · 0/40 citizens false-flagged.

## Narrative Tracker

Clusters posts into narrative "atoms" via MinHash + LSH (threshold 0.45).  
For each atom:
- Identifies seed (earliest post) as origin point
- Builds directed provenance graph (amplification edges)
- Computes spread velocity (accounts/hour in first 30 minutes)
- Classifies account roles: origin / early_spreader / amplifier / late_adopter
- Counts mutations (same narrative, different wording)

## Prebunking Engine

Detects active manipulation techniques from CIB + Tracker signals:
- `coordinated_amplification` — high reciprocity clusters
- `copy_paste_campaign` — many duplicate post pairs
- `astroturfing` — many new accounts with high metadata score
- `velocity_manipulation` — fast narrative + CIB involvement
- `source_transparency` — always included

Generates cards in Albanian (sq), German (de), English (en).  
Uses Groq API (Llama 3.3 70B) if configured; falls back to curated templates.

## Blockchain Anchoring

- Hash: keccak256 of canonical JSON (keys sorted)
- Contract: `0x1F04BCD4C6B97D201654F2Aa2a9F3cf91A35Ab33` on Polygon Amoy
- Function: `storeHash(bytes32 reportHash, string reportId)`
- Fallback: local-only record with `pending_reason` if wallet not configured

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Health check |
| POST | `/analyze` | Raw CIB report |
| POST | `/dashboard` | CIB + dashboard payload |
| POST | `/full` | Complete pipeline (all modules) |
| GET | `/demo` | Pre-computed demo run |
| GET | `/reports` | List stored reports |
| GET | `/reports/{id}` | Get stored report |
| POST | `/prebunk` | Generate prebunking for stored report |

## Deployment

| Service | Platform | Config |
|---------|----------|--------|
| API | Render | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Frontend | Vercel | Next.js auto-detect, root: `frontend/` |
| Database | Neon PostgreSQL | `DATABASE_URL` env var |
| Cache | Upstash Redis | `UPSTASH_REDIS_REST_URL` + `_TOKEN` |

## Environment Variables

```
# API (Render)
DATABASE_URL=postgresql://...
UPSTASH_REDIS_REST_URL=https://...
UPSTASH_REDIS_REST_TOKEN=...
GROQ_API_KEY=...
WALLET_PRIVATE_KEY=...
POLYGON_RPC_URL=https://rpc-amoy.polygon.technology
ALLOWED_ORIGINS=https://narrativ.vercel.app

# Frontend (Vercel)
NEXT_PUBLIC_API_URL=https://narrativ-api.onrender.com
```

## ATIP Compatibility

Engine output maps directly to ATIP surfaces without transformation:

| NARRATIV field | ATIP surface |
|----------------|-------------|
| `cib.graph` | Network Graph view |
| `cib.clusters` | Campaign Tracker entries |
| `cib.flagged_accounts` | Review queue |
| `cib.tlp` | TLP classification |
| `cib.duplicate_evidence` | Evidence export |

## Input Layer (Connectors)

| Connector | Source | Config |
|-----------|--------|--------|
| CSV import | Any exported dataset | No config needed |
| JSON upload | Raw Post/Account JSON | No config needed |
| Twitter/X | API v2 search | `TWITTER_BEARER_TOKEN` |
| Telegram | Public channel messages | `TELEGRAM_API_ID` + `TELEGRAM_API_HASH` |

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/ingest/upload` | CSV or JSON file → full analysis |
| POST | `/ingest/twitter` | Twitter query → full analysis |
| POST | `/ingest/telegram` | Telegram channels → full analysis |
| GET | `/monitor` | List scheduled jobs |
| POST | `/monitor` | Add monitoring job |
| DELETE | `/monitor/{id}` | Remove monitoring job |

### Scheduler

Automated monitoring via APScheduler — runs CIB analysis at configured
intervals and sends webhook alerts when flagged accounts exceed threshold.
