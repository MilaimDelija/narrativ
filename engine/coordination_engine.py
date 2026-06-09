"""
Coordination Engine — Coordinated Inauthentic Behaviour (CIB) detection
=======================================================================

A defensive analysis module: it surfaces *statistical traces of orchestration*
(fake-account networks, paid amplification masked as organic, time-synced
botnets) and hands an analyst the evidence. It does NOT decide what is "true",
it does NOT suppress content, and it never acts automatically.

Design constraints (these are the ethics, encoded):
  1. Evidence over verdict. Output is "these N accounts show these M signals,
     here is the proof", never "this is fake — remove it".
  2. Human-in-the-loop is mandatory. The engine produces a review packet for
     an analyst; it has no enforcement path.
  3. Conservative by default. Authentic civic movements ALSO coordinate
     (organisers ask people to use a hashtag). The only thing that separates
     them from CIB is *deception* — fake accounts, hidden orchestration, paid
     reach disguised as organic. Thresholds are high and tunable, and the
     report always states the false-positive risk.
  4. Symmetry. Run it on every side of a debate or you are a propagandist,
     not a defender. The engine is content-agnostic on purpose.

Plugs into ATIP: emits a TLP-classified evidence packet compatible with the
Campaign Tracker, and a node/edge graph compatible with the Network Graph view.

Author: Neuronium Engineers
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional

import networkx as nx
import numpy as np
from datasketch import MinHash, MinHashLSH


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Post:
    """A single piece of content on the network."""
    post_id: str
    account_id: str
    timestamp: datetime          # tz-aware, UTC
    text: str
    hashtags: tuple[str, ...] = ()
    # who this post amplifies (retweet/quote/share target account_id), if any
    amplifies_account: Optional[str] = None
    media_hash: Optional[str] = None   # perceptual hash of attached media
    is_sponsored: bool = False         # platform-disclosed paid / ad


@dataclass
class Account:
    """Account-level metadata used for anomaly features."""
    account_id: str
    created_at: datetime
    followers: int
    following: int
    has_default_avatar: bool = False
    display_name: str = ""
    handle: str = ""


@dataclass
class CoordinationSignals:
    """Per-account signal breakdown. Each field is in [0, 1]."""
    temporal: float = 0.0       # co-activity in tight time windows
    content: float = 0.0        # near-duplicate / semantic content reuse
    network: float = 0.0        # membership in a dense mutual-amplification cluster
    metadata: float = 0.0       # account-level anomalies (age burst, default pfp, ...)

    def as_dict(self) -> dict[str, float]:
        return {
            "temporal": round(self.temporal, 4),
            "content": round(self.content, 4),
            "network": round(self.network, 4),
            "metadata": round(self.metadata, 4),
        }


# ---------------------------------------------------------------------------
# 1. Temporal coordination
# ---------------------------------------------------------------------------

class TemporalAnalyzer:
    """
    Detects accounts that act in lockstep. Authentic activity is bursty but
    individually irregular; orchestrated activity shows pairs of accounts
    repeatedly posting within the same narrow window.

    Method: bucket posts into `window_seconds` slots, count co-occurrences
    per account pair, then score each account by how often it co-fires with
    others beyond chance.
    """

    def __init__(self, window_seconds: int = 60, min_co_events: int = 3):
        self.window = window_seconds
        self.min_co_events = min_co_events

    def score(self, posts: list[Post]) -> dict[str, float]:
        # account -> set of time buckets it was active in
        buckets: dict[str, set[int]] = defaultdict(set)
        for p in posts:
            slot = int(p.timestamp.timestamp() // self.window)
            buckets[p.account_id].add(slot)

        accounts = list(buckets)
        co_events: dict[str, int] = defaultdict(int)
        for i in range(len(accounts)):
            for j in range(i + 1, len(accounts)):
                a, b = accounts[i], accounts[j]
                shared = len(buckets[a] & buckets[b])
                if shared >= self.min_co_events:
                    co_events[a] += shared
                    co_events[b] += shared

        if not co_events:
            return {a: 0.0 for a in accounts}

        # normalise by the busiest co-firing account, log-scaled to avoid
        # one extreme account flattening everyone else
        peak = max(co_events.values())
        return {
            a: (math.log1p(co_events.get(a, 0)) / math.log1p(peak)) if peak else 0.0
            for a in accounts
        }


# ---------------------------------------------------------------------------
# 2. Content similarity (near-duplicate + semantic)
# ---------------------------------------------------------------------------

# An embedding function maps a string -> vector. Pluggable: swap in
# sentence-transformers locally, or a Groq/hosted embedding endpoint.
EmbedFn = Callable[[list[str]], np.ndarray]


class ContentAnalyzer:
    """
    Two layers:
      (a) Near-duplicate detection via MinHash + LSH (fast, catches copypasta
          and lightly edited reposts even across millions of items).
      (b) Optional semantic clustering via embeddings (catches paraphrased
          message discipline that MinHash misses).
    """

    def __init__(self, lsh_threshold: float = 0.7, num_perm: int = 128,
                 embed_fn: Optional[EmbedFn] = None, semantic_threshold: float = 0.85):
        self.lsh_threshold = lsh_threshold
        self.num_perm = num_perm
        self.embed_fn = embed_fn
        self.semantic_threshold = semantic_threshold

    @staticmethod
    def _shingles(text: str, k: int = 3) -> set[str]:
        tokens = text.lower().split()
        if len(tokens) < k:
            return {" ".join(tokens)} if tokens else set()
        return {" ".join(tokens[i:i + k]) for i in range(len(tokens) - k + 1)}

    def _minhash(self, text: str) -> MinHash:
        m = MinHash(num_perm=self.num_perm)
        for sh in self._shingles(text):
            m.update(sh.encode("utf-8"))
        return m

    def score(self, posts: list[Post]) -> tuple[dict[str, float], list[tuple[str, str]]]:
        """Returns (per-account content score, list of duplicate post pairs)."""
        lsh = MinHashLSH(threshold=self.lsh_threshold, num_perm=self.num_perm)
        minhashes: dict[str, MinHash] = {}
        for p in posts:
            if not p.text.strip():
                continue
            mh = self._minhash(p.text)
            minhashes[p.post_id] = mh
            lsh.insert(p.post_id, mh)

        post_owner = {p.post_id: p.account_id for p in posts}
        dup_pairs: list[tuple[str, str]] = []
        account_dups: dict[str, int] = defaultdict(int)

        seen: set[frozenset] = set()
        for pid, mh in minhashes.items():
            matches = [m for m in lsh.query(mh) if m != pid]
            for m in matches:
                key = frozenset((pid, m))
                if key in seen:
                    continue
                seen.add(key)
                # only count cross-account reuse — self-reposts are not CIB
                if post_owner[pid] != post_owner[m]:
                    dup_pairs.append((pid, m))
                    account_dups[post_owner[pid]] += 1
                    account_dups[post_owner[m]] += 1

        # optional semantic layer
        if self.embed_fn is not None:
            self._add_semantic(posts, post_owner, account_dups)

        accounts = {p.account_id for p in posts}
        peak = max(account_dups.values()) if account_dups else 0
        scores = {
            a: (math.log1p(account_dups.get(a, 0)) / math.log1p(peak)) if peak else 0.0
            for a in accounts
        }
        return scores, dup_pairs

    def _add_semantic(self, posts, post_owner, account_dups) -> None:
        texts = [p.text for p in posts if p.text.strip()]
        ids = [p.post_id for p in posts if p.text.strip()]
        if len(texts) < 2:
            return
        vecs = self.embed_fn(texts)
        vecs = vecs / (np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9)
        sim = vecs @ vecs.T
        n = len(ids)
        for i in range(n):
            for j in range(i + 1, n):
                if sim[i, j] >= self.semantic_threshold:
                    a, b = post_owner[ids[i]], post_owner[ids[j]]
                    if a != b:
                        account_dups[a] += 1
                        account_dups[b] += 1


# ---------------------------------------------------------------------------
# 3. Network structure
# ---------------------------------------------------------------------------

class NetworkAnalyzer:
    """
    Builds a directed amplification graph (A -> B means A amplified B) and finds
    densely mutually-amplifying clusters via greedy modularity (Louvain-style).

    A cluster is suspicious when internal reciprocity is high and the cluster
    is large enough that organic explanation is unlikely. Real movements have
    *some* mutual amplification; the flag is for unusually closed, dense rings.
    """

    def __init__(self, min_cluster_size: int = 4, reciprocity_flag: float = 0.6):
        self.min_cluster_size = min_cluster_size
        self.reciprocity_flag = reciprocity_flag

    def build_graph(self, posts: list[Post]) -> nx.DiGraph:
        g = nx.DiGraph()
        for p in posts:
            g.add_node(p.account_id)
            if p.amplifies_account and p.amplifies_account != p.account_id:
                if g.has_edge(p.account_id, p.amplifies_account):
                    g[p.account_id][p.amplifies_account]["weight"] += 1
                else:
                    g.add_edge(p.account_id, p.amplifies_account, weight=1)
        return g

    def score(self, posts: list[Post]) -> tuple[dict[str, float], list[dict], nx.DiGraph]:
        g = self.build_graph(posts)
        undirected = g.to_undirected()

        scores: dict[str, float] = {n: 0.0 for n in g.nodes}
        clusters_report: list[dict] = []

        if undirected.number_of_edges() == 0:
            return scores, clusters_report, g

        communities = nx.community.greedy_modularity_communities(undirected)
        for idx, comm in enumerate(communities):
            members = list(comm)
            if len(members) < self.min_cluster_size:
                continue
            sub = g.subgraph(members)
            recip = nx.reciprocity(sub) or 0.0
            density = nx.density(sub)
            # cluster suspicion: high reciprocity AND high internal density
            suspicion = min(1.0, (recip * 0.6 + density * 0.4) *
                            (1.0 if recip >= self.reciprocity_flag else 0.5))
            for m in members:
                scores[m] = max(scores[m], suspicion)
            if recip >= self.reciprocity_flag:
                clusters_report.append({
                    "cluster_id": idx,
                    "size": len(members),
                    "members": members,
                    "reciprocity": round(recip, 3),
                    "density": round(density, 3),
                    "suspicion": round(suspicion, 3),
                })
        return scores, clusters_report, g


# ---------------------------------------------------------------------------
# 4. Account metadata anomalies
# ---------------------------------------------------------------------------

class MetadataAnalyzer:
    """
    Account-level red flags. None is conclusive alone; they raise prior
    suspicion that the network/content/temporal layers must then confirm.
    """

    def __init__(self, reference_time: Optional[datetime] = None,
                 young_account_days: int = 30, burst_window_days: int = 7):
        self.now = reference_time or datetime.now(timezone.utc)
        self.young_days = young_account_days
        self.burst_window_days = burst_window_days

    def score(self, accounts: list[Account]) -> dict[str, float]:
        if not accounts:
            return {}

        # detect creation-date bursts: many accounts born in the same week
        week_counts: dict[int, int] = defaultdict(int)
        for a in accounts:
            week = int(a.created_at.timestamp() // (self.burst_window_days * 86400))
            week_counts[week] += 1
        burst_weeks = {w for w, c in week_counts.items() if c >= max(3, len(accounts) * 0.15)}

        scores: dict[str, float] = {}
        for a in accounts:
            flags = 0.0
            age_days = (self.now - a.created_at).days
            if age_days <= self.young_days:
                flags += 0.30
            week = int(a.created_at.timestamp() // (self.burst_window_days * 86400))
            if week in burst_weeks:
                flags += 0.25
            if a.has_default_avatar:
                flags += 0.15
            # follower/following imbalance typical of amplifier accounts
            if a.following > 0 and a.followers / max(a.following, 1) < 0.05:
                flags += 0.15
            # handle pattern: name + long digit run
            if any(ch.isdigit() for ch in a.handle[-4:]) and sum(
                    c.isdigit() for c in a.handle) >= 4:
                flags += 0.15
            scores[a.account_id] = min(1.0, flags)
        return scores


# ---------------------------------------------------------------------------
# Combined scoring + report
# ---------------------------------------------------------------------------

@dataclass
class EngineConfig:
    weights: dict[str, float] = field(default_factory=lambda: {
        "temporal": 0.30, "content": 0.30, "network": 0.25, "metadata": 0.15,
    })
    # accounts below this combined score are not reported at all (conservative)
    review_threshold: float = 0.55
    # at least this many independent signals must be non-trivial to flag,
    # so a single noisy axis can never flag an account alone
    min_active_signals: int = 2
    active_signal_floor: float = 0.25
    tlp: str = "TLP:AMBER"


class CoordinationEngine:
    def __init__(self, config: Optional[EngineConfig] = None,
                 embed_fn: Optional[EmbedFn] = None,
                 reference_time: Optional[datetime] = None):
        self.cfg = config or EngineConfig()
        self.temporal = TemporalAnalyzer()
        self.content = ContentAnalyzer(embed_fn=embed_fn)
        self.network = NetworkAnalyzer()
        self.metadata = MetadataAnalyzer(reference_time=reference_time)

    def analyze(self, posts: list[Post], accounts: list[Account]) -> dict:
        t_scores = self.temporal.score(posts)
        c_scores, dup_pairs = self.content.score(posts)
        n_scores, clusters, graph = self.network.score(posts)
        m_scores = self.metadata.score(accounts)

        all_ids = {p.account_id for p in posts} | {a.account_id for a in accounts}
        per_account: dict[str, dict] = {}

        for aid in all_ids:
            sig = CoordinationSignals(
                temporal=t_scores.get(aid, 0.0),
                content=c_scores.get(aid, 0.0),
                network=n_scores.get(aid, 0.0),
                metadata=m_scores.get(aid, 0.0),
            )
            w = self.cfg.weights
            combined = (sig.temporal * w["temporal"] + sig.content * w["content"] +
                        sig.network * w["network"] + sig.metadata * w["metadata"])
            active = sum(1 for v in sig.as_dict().values()
                         if v >= self.cfg.active_signal_floor)
            per_account[aid] = {
                "account_id": aid,
                "signals": sig.as_dict(),
                "combined_score": round(combined, 4),
                "active_signals": active,
                "flagged_for_review": (
                    combined >= self.cfg.review_threshold
                    and active >= self.cfg.min_active_signals
                ),
            }

        flagged = sorted(
            (a for a in per_account.values() if a["flagged_for_review"]),
            key=lambda x: x["combined_score"], reverse=True,
        )

        return self._build_report(per_account, flagged, clusters, dup_pairs, graph,
                                   total_accounts=len(all_ids), total_posts=len(posts))

    # ----- ATIP-compatible evidence packet -----
    def _build_report(self, per_account, flagged, clusters, dup_pairs, graph,
                      total_accounts, total_posts) -> dict:
        fp_note = (
            "Authentic civic movements also coordinate (organisers spread a "
            "hashtag, supporters repost). A high score is NOT proof of "
            "inauthenticity — it is a prompt for human review of the listed "
            "evidence. Do not enforce on this output."
        )
        return {
            "tlp": self.cfg.tlp,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_accounts": total_accounts,
                "total_posts": total_posts,
                "flagged_for_review": len(flagged),
                "suspicious_clusters": len(clusters),
                "cross_account_duplicate_pairs": len(dup_pairs),
            },
            "false_positive_warning": fp_note,
            "flagged_accounts": flagged,
            "clusters": clusters,
            "duplicate_evidence": dup_pairs[:200],  # cap for the packet
            # node/edge form for ATIP Network Graph
            "graph": {
                "nodes": [
                    {"id": n, "score": per_account.get(n, {}).get("combined_score", 0.0)}
                    for n in graph.nodes
                ],
                "edges": [
                    {"source": u, "target": v, "weight": d.get("weight", 1)}
                    for u, v, d in graph.edges(data=True)
                ],
            },
            "config": {
                "weights": self.cfg.weights,
                "review_threshold": self.cfg.review_threshold,
                "min_active_signals": self.cfg.min_active_signals,
            },
        }
