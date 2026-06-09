"""
Demo: synthetic dataset with a genuine civic movement + an injected
coordinated network, to verify the engine flags the orchestration WITHOUT
flagging the authentic crowd.

Run:  python demo.py
"""
import json
import random
from datetime import datetime, timedelta, timezone

from coordination_engine import Account, CoordinationEngine, Post

random.seed(42)
BASE = datetime(2026, 6, 8, 18, 0, 0, tzinfo=timezone.utc)
HASHTAG = "#protesta"

posts: list[Post] = []
accounts: list[Account] = []
pid = 0


def new_post(account_id, minute_offset, text, amplifies=None):
    global pid
    pid += 1
    return Post(
        post_id=f"p{pid}",
        account_id=account_id,
        timestamp=BASE + timedelta(minutes=minute_offset),
        text=text,
        hashtags=(HASHTAG,),
        amplifies_account=amplifies,
    )


# --- (A) authentic civic crowd: 40 real people, irregular timing, varied text
organic_phrases = [
    "Sot dola në shesh sepse më intereson e ardhmja e vendit {h}",
    "Atmosferë e qetë, shumë familje me fëmijë këtu {h}",
    "Kërkojmë llogaridhënie, asgjë më shumë {h}",
    "U lodha por ia vlejti, shihemi nesër {h}",
    "Policia e qetë, protestuesit gjithashtu {h}",
    "Erdha vetë, askush nuk më pagoi për këtë {h}",
    "Shpresoj që zëri ynë të dëgjohet {h}",
    "Foto nga sheshi, plot njerëz {h}",
]
for i in range(40):
    aid = f"citizen_{i}"
    accounts.append(Account(
        account_id=aid,
        created_at=BASE - timedelta(days=random.randint(200, 3000)),
        followers=random.randint(80, 4000),
        following=random.randint(100, 1500),
        has_default_avatar=random.random() < 0.05,
        handle=f"user_{random.choice(['ana','ben','dri','eli','fitim'])}{i}",
    ))
    for _ in range(random.randint(1, 4)):
        minute = random.uniform(0, 240)        # spread over 4 hours
        text = random.choice(organic_phrases).format(h=HASHTAG)
        # they sometimes amplify a few popular real voices, loosely
        amp = f"citizen_{random.randint(0, 5)}" if random.random() < 0.25 else None
        posts.append(new_post(aid, minute, text, amp))

# --- (B) injected coordinated network: 12 fake accounts, born same week,
#         lockstep posting, near-identical copy, mutual amplification ring
COORD_COPY = "Qeveria duhet të largohet TANI ndajeni kudo #protesta #ndryshim"
coord_ids = [f"bot_{i}" for i in range(12)]
burst_birth = BASE - timedelta(days=5)        # all created within one week
for i, aid in enumerate(coord_ids):
    accounts.append(Account(
        account_id=aid,
        created_at=burst_birth - timedelta(days=random.randint(0, 4)),
        followers=random.randint(2, 40),
        following=random.randint(400, 2000),   # follow many, followed by few
        has_default_avatar=True,
        handle=f"patriot{random.randint(10000, 99999)}",
    ))

# three synchronized waves; within each wave all bots fire in the same minute
for wave_minute in (45, 95, 160):
    for i, aid in enumerate(coord_ids):
        jitter = random.uniform(0, 0.4)        # sub-minute jitter = same bucket
        posts.append(new_post(aid, wave_minute + jitter, COORD_COPY))
        # mutual amplification pod: each bot boosts both neighbours (reciprocal)
        nxt = coord_ids[(i + 1) % len(coord_ids)]
        prv = coord_ids[(i - 1) % len(coord_ids)]
        posts.append(new_post(aid, wave_minute + jitter + 0.1, COORD_COPY, amplifies=nxt))
        posts.append(new_post(aid, wave_minute + jitter + 0.2, COORD_COPY, amplifies=prv))

# --- (C) disclosed paid: 5 legitimate promoted accounts, transparently
#         sponsored, spread out, varied text — should land in the PAID bucket,
#         NOT the coordinated one (disclosure is honest, behaviour is normal).
paid_ids = [f"promoted_{i}" for i in range(5)]
paid_copy = [
    "Mbështetni kauzën, mësoni më shumë në linkun {h}",
    "Event informues nesër në qendër {h}",
    "Sponsored: udhëzues për pjesëmarrje paqësore {h}",
]
for i, aid in enumerate(paid_ids):
    accounts.append(Account(
        account_id=aid,
        created_at=BASE - timedelta(days=random.randint(300, 1500)),
        followers=random.randint(5000, 80000),   # real orgs, large reach
        following=random.randint(50, 600),
        has_default_avatar=False,
        handle=f"org_{['media','ngo','forum','civic','press'][i]}",
    ))
    for _ in range(random.randint(2, 4)):
        minute = random.uniform(60, 240)
        text = random.choice(paid_copy).format(h=HASHTAG)
        posts.append(new_post(aid, minute, text))
        posts[-1].is_sponsored = True

# --- run the engine
engine = CoordinationEngine(reference_time=BASE)
report = engine.analyze(posts, accounts)

print("=" * 70)
print("CIB ANALYSIS REPORT")
print("=" * 70)
print(f"TLP: {report['tlp']}")
print("Summary:", json.dumps(report["summary"], indent=2))
print("\nWarning:", report["false_positive_warning"])

print("\n--- Flagged accounts (top 15) ---")
for a in report["flagged_accounts"][:15]:
    print(f"  {a['account_id']:14s} score={a['combined_score']:.3f} "
          f"signals={a['signals']}")

print(f"\n--- Suspicious clusters: {len(report['clusters'])} ---")
for c in report["clusters"]:
    print(f"  cluster {c['cluster_id']}: size={c['size']} "
          f"reciprocity={c['reciprocity']} density={c['density']} "
          f"suspicion={c['suspicion']}")

# verification: did we catch the bots without flagging the citizens?
flagged_ids = {a["account_id"] for a in report["flagged_accounts"]}
bots_caught = sum(1 for b in coord_ids if b in flagged_ids)
citizens_flagged = sum(1 for a in flagged_ids if a.startswith("citizen_"))
print("\n" + "=" * 70)
print("VERIFICATION")
print("=" * 70)
print(f"Coordinated accounts caught:   {bots_caught}/{len(coord_ids)}")
print(f"Authentic citizens false-flagged: {citizens_flagged}/40")
