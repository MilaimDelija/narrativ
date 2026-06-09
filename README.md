# NARRATIV

**Open infrastructure for influence operation detection.**

Detects coordinated inauthentic behaviour (CIB), maps narrative provenance, and surfaces reach transparency — built for civil society, journalists, and researchers.

> This system never suppresses content and never acts automatically. Output is always a review packet for a human analyst, never a verdict.

## Architecture

```
narrativ/
├── engine/          # CIB detection engine (Python)
├── api/             # FastAPI backend (Render)
├── frontend/        # Next.js dashboard (Vercel)
└── docs/            # Architecture and methodology
```

## Engine — Quick Start

```bash
cd engine
pip install -r requirements.txt
python demo.py
```

Expected output: 12/12 coordinated accounts caught, 0/40 authentic citizens false-flagged.

## Four Signal Layers

1. **Temporal** — lockstep posting within 60-second windows
2. **Content** — MinHash + LSH near-duplicate detection (datasketch, threshold 0.7)
3. **Network** — Louvain-style community detection on amplification graph (NetworkX)
4. **Metadata** — account-age bursts, default avatars, follower imbalance, handle patterns

A combined score is reported only when ≥ 0.55 AND ≥ 2 independent signal layers fire.

## ATIP Compatibility

Engine output maps directly to ATIP surfaces:
- `report["graph"]` → Network Graph view
- `report["clusters"]` → Campaign Tracker
- `report["tlp"]` → TLP classification (default `TLP:AMBER`)

## Stack

| Layer | Technology |
|-------|-----------|
| CIB Engine | Python + networkx + datasketch |
| Dashboard | Next.js + React + recharts |
| Backend API | FastAPI |
| Blockchain | Polygon Amoy (audit anchoring) |
| LLM | Groq API — Llama 3.3 70B |
| Database | Neon PostgreSQL |
| Cache | Upstash Redis |

## Ethical Design Constraints

1. **Evidence, not verdict** — output is `N accounts show M signals`, never `remove this`
2. **Human-in-the-loop mandatory** — no enforcement path exists in the engine
3. **Conservative by default** — authentic civic movements also coordinate; only deception is flagged
4. **Symmetry** — run on all sides of a debate or you are a propagandist, not a defender

---

Neuronium Engineers — Schlüchtern, Germany — June 2026
