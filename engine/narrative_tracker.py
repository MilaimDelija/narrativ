"""
Narrative Tracker — cross-account provenance mapping
=====================================================

Tracks how narrative "atoms" originate and spread across accounts and time.
A narrative atom is a distinct claim or framing, identified by semantic
clustering of post content.

Key questions answered:
  - Where did this framing first appear?
  - Which accounts amplified it and in what order?
  - How did the framing mutate as it spread?
  - Which accounts are original sources vs amplifiers?

Design constraints (same as CIB engine):
  - No content suppression, no automatic action
  - Output is evidence for human analyst review
  - Works on public data only
  - Content-agnostic: run on all sides of a debate

Author: Neuronium Engineers
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

import networkx as nx
import numpy as np
from datasketch import MinHash, MinHashLSH

# Re-use Post from the CIB engine
from coordination_engine import Post


# ── Data model ────────────────────────────────────────────────────────────

@dataclass
class NarrativeAtom:
    """A distinct narrative claim or framing detected across posts."""
    atom_id: str
    seed_post_id: str           # earliest post carrying this narrative
    seed_account_id: str
    seed_timestamp: datetime
    representative_text: str    # text of the seed post (truncated)
    member_post_ids: list[str] = field(default_factory=list)
    member_account_ids: list[str] = field(default_factory=list)
    spread_duration_minutes: float = 0.0
    mutation_count: int = 0     # posts with same narrative but different text


@dataclass
class ProvenanceNode:
    account_id: str
    post_id: str
    timestamp: datetime
    text_snippet: str
    role: str                   # "origin" | "early_spreader" | "amplifier" | "late_adopter"
    minute_offset: float        # minutes after seed


@dataclass
class NarrativeChain:
    """Full provenance chain for one narrative atom."""
    atom: NarrativeAtom
    nodes: list[ProvenanceNode]
    graph: nx.DiGraph            # directed spread graph
    velocity: float              # accounts/hour in first 30 min
    reach_estimate: float        # sum of 1+log(followers) across chain


# ── Text preprocessing ────────────────────────────────────────────────────

_URL_RE  = re.compile(r"https?://\S+")
_TAG_RE  = re.compile(r"[@#]\w+")
_WS_RE   = re.compile(r"\s+")

def _normalize(text: str) -> str:
    text = _URL_RE.sub("", text)
    text = _TAG_RE.sub("", text)
    text = _WS_RE.sub(" ", text).strip().lower()
    return text

def _shingles(text: str, k: int = 3) -> set[str]:
    tokens = text.split()
    if len(tokens) < k:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[i:i+k]) for i in range(len(tokens) - k + 1)}

def _minhash(text: str, num_perm: int = 128) -> MinHash:
    m = MinHash(num_perm=num_perm)
    for sh in _shingles(_normalize(text)):
        m.update(sh.encode("utf-8"))
    return m

def _atom_id(seed_post_id: str, seed_text: str) -> str:
    h = hashlib.sha256(f"{seed_post_id}:{seed_text}".encode()).hexdigest()[:12]
    return f"atom_{h}"


# ── Narrative clustering ──────────────────────────────────────────────────

class NarrativeClusterer:
    """
    Clusters posts into narrative atoms using MinHash + LSH.
    Each cluster represents a distinct framing; the earliest post
    in each cluster is the seed (origin point).
    """

    def __init__(self, similarity_threshold: float = 0.45, num_perm: int = 128,
                 min_cluster_size: int = 2):
        self.threshold = similarity_threshold
        self.num_perm = num_perm
        self.min_size = min_cluster_size

    def cluster(self, posts: list[Post]) -> list[NarrativeAtom]:
        nonempty = [p for p in posts if _normalize(p.text)]
        if not nonempty:
            return []

        lsh = MinHashLSH(threshold=self.threshold, num_perm=self.num_perm)
        minhashes: dict[str, MinHash] = {}
        for p in nonempty:
            mh = _minhash(p.text, self.num_perm)
            minhashes[p.post_id] = mh
            lsh.insert(p.post_id, mh)

        # Union-Find to group similar posts
        parent = {p.post_id: p.post_id for p in nonempty}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            parent[find(a)] = find(b)

        seen: set[frozenset] = set()
        for p in nonempty:
            for match in lsh.query(minhashes[p.post_id]):
                if match == p.post_id:
                    continue
                key = frozenset((p.post_id, match))
                if key not in seen:
                    seen.add(key)
                    union(p.post_id, match)

        # Group by root
        groups: dict[str, list[Post]] = defaultdict(list)
        post_by_id = {p.post_id: p for p in nonempty}
        for p in nonempty:
            groups[find(p.post_id)].append(p)

        atoms: list[NarrativeAtom] = []
        for root, members in groups.items():
            if len(members) < self.min_size:
                continue
            members_sorted = sorted(members, key=lambda p: p.timestamp)
            seed = members_sorted[0]
            latest = members_sorted[-1]
            duration = (latest.timestamp - seed.timestamp).total_seconds() / 60

            # Count mutations: posts that share the narrative but differ in text
            unique_texts = len({_normalize(p.text) for p in members})
            mutations = max(0, unique_texts - 1)

            atom = NarrativeAtom(
                atom_id=_atom_id(seed.post_id, seed.text),
                seed_post_id=seed.post_id,
                seed_account_id=seed.account_id,
                seed_timestamp=seed.timestamp,
                representative_text=seed.text[:200],
                member_post_ids=[p.post_id for p in members_sorted],
                member_account_ids=list(dict.fromkeys(p.account_id for p in members_sorted)),
                spread_duration_minutes=round(duration, 1),
                mutation_count=mutations,
            )
            atoms.append(atom)

        return sorted(atoms, key=lambda a: a.seed_timestamp)


# ── Provenance chain builder ──────────────────────────────────────────────

def _role(offset_minutes: float, total_duration: float) -> str:
    if offset_minutes == 0:
        return "origin"
    if total_duration == 0:
        return "amplifier"
    ratio = offset_minutes / max(total_duration, 1)
    if ratio < 0.15:
        return "early_spreader"
    if ratio < 0.6:
        return "amplifier"
    return "late_adopter"


def _reach_weight(followers: int) -> float:
    return 1.0 + math.log1p(max(0, followers))


def build_provenance_chain(
    atom: NarrativeAtom,
    posts: list[Post],
    follower_map: dict[str, int],
    amplification_map: dict[str, str],   # post_id -> amplifies_account_id
) -> NarrativeChain:
    """
    Build a directed provenance graph for one narrative atom.
    Edges represent amplification relationships between accounts.
    """
    pid_set = set(atom.member_post_ids)
    member_posts = [p for p in posts if p.post_id in pid_set]
    member_posts.sort(key=lambda p: p.timestamp)

    seed_ts = atom.seed_timestamp
    duration = atom.spread_duration_minutes

    nodes: list[ProvenanceNode] = []
    g = nx.DiGraph()
    reach_total = 0.0

    account_first_post: dict[str, datetime] = {}
    for p in member_posts:
        if p.account_id not in account_first_post:
            account_first_post[p.account_id] = p.timestamp

    for p in member_posts:
        offset = (p.timestamp - seed_ts).total_seconds() / 60
        role = _role(offset if p.account_id == atom.seed_account_id or
                     account_first_post.get(p.account_id) == p.timestamp else offset,
                     duration)
        # Use the first-appearance offset for this account
        first_offset = (account_first_post[p.account_id] - seed_ts).total_seconds() / 60
        node = ProvenanceNode(
            account_id=p.account_id,
            post_id=p.post_id,
            timestamp=p.timestamp,
            text_snippet=p.text[:120],
            role=_role(first_offset, duration),
            minute_offset=round(first_offset, 1),
        )
        nodes.append(node)
        g.add_node(p.account_id, role=node.role, minute_offset=round(first_offset, 1))
        reach_total += _reach_weight(follower_map.get(p.account_id, 0))

        amp = amplification_map.get(p.post_id)
        if amp and amp in {q.account_id for q in member_posts}:
            g.add_edge(p.account_id, amp, post_id=p.post_id)

    # Velocity: unique accounts in first 30 minutes
    early = [n for n in nodes if n.minute_offset <= 30]
    early_accounts = len({n.account_id for n in early})
    velocity = (early_accounts / 0.5) if early_accounts else 0  # accounts per hour

    return NarrativeChain(
        atom=atom,
        nodes=nodes,
        graph=g,
        velocity=round(velocity, 1),
        reach_estimate=round(reach_total, 1),
    )


# ── Main tracker ──────────────────────────────────────────────────────────

class NarrativeTracker:
    """
    Top-level narrative tracking interface.
    Takes posts and optional account follower data, returns provenance chains
    for all detected narrative atoms.
    """

    def __init__(self, similarity_threshold: float = 0.45, min_cluster_size: int = 2):
        self.clusterer = NarrativeClusterer(
            similarity_threshold=similarity_threshold,
            min_cluster_size=min_cluster_size,
        )

    def track(self,
              posts: list[Post],
              follower_map: Optional[dict[str, int]] = None) -> dict:
        """
        Returns a tracker report compatible with the API response format.
        """
        fm = follower_map or {}
        amp_map = {p.post_id: p.amplifies_account
                   for p in posts if p.amplifies_account}

        atoms = self.clusterer.cluster(posts)
        chains: list[NarrativeChain] = []
        for atom in atoms:
            chain = build_provenance_chain(atom, posts, fm, amp_map)
            chains.append(chain)

        # Sort by reach (most impactful first)
        chains.sort(key=lambda c: c.reach_estimate, reverse=True)

        return self._build_report(chains, posts)

    def _build_report(self, chains: list[NarrativeChain], posts: list[Post]) -> dict:
        narratives_out = []
        for chain in chains:
            a = chain.atom
            narratives_out.append({
                "atom_id": a.atom_id,
                "origin": {
                    "account_id": a.seed_account_id,
                    "post_id": a.seed_post_id,
                    "timestamp": a.seed_timestamp.isoformat(),
                    "text": a.representative_text,
                },
                "spread": {
                    "total_accounts": len(a.member_account_ids),
                    "total_posts": len(a.member_post_ids),
                    "duration_minutes": a.spread_duration_minutes,
                    "velocity_accounts_per_hour": chain.velocity,
                    "mutation_count": a.mutation_count,
                    "reach_estimate": chain.reach_estimate,
                },
                "provenance_chain": [
                    {
                        "account_id": n.account_id,
                        "post_id": n.post_id,
                        "timestamp": n.timestamp.isoformat(),
                        "role": n.role,
                        "minute_offset": n.minute_offset,
                        "text_snippet": n.text_snippet,
                    }
                    for n in sorted(chain.nodes, key=lambda x: x.minute_offset)
                ],
                "graph": {
                    "nodes": [
                        {"id": n, "role": d.get("role", "amplifier"),
                         "minute_offset": d.get("minute_offset", 0)}
                        for n, d in chain.graph.nodes(data=True)
                    ],
                    "edges": [
                        {"source": u, "target": v}
                        for u, v in chain.graph.edges()
                    ],
                },
            })

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_posts_analyzed": len(posts),
            "narrative_atoms_detected": len(chains),
            "narratives": narratives_out,
            "summary": {
                "top_origin_accounts": list(dict.fromkeys(
                    c.atom.seed_account_id for c in chains[:10]
                )),
                "fastest_spreading": (
                    chains[0].atom.atom_id
                    if chains else None
                ),
                "highest_reach": (
                    max(chains, key=lambda c: c.reach_estimate).atom.atom_id
                    if chains else None
                ),
            },
        }
