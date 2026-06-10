"""
Twitter/X connector — uses API v2 (Bearer Token).
Fetches recent tweets for a hashtag or keyword query,
normalises them to Post + Account format.

Required env var: TWITTER_BEARER_TOKEN
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

import httpx

from coordination_engine import Post, Account
from .base import BaseConnector, ConnectorResult

TWITTER_API = "https://api.twitter.com/2"


class TwitterConnector(BaseConnector):
    source_name = "twitter"

    def __init__(self, bearer_token: Optional[str] = None):
        self.token = bearer_token or os.getenv("TWITTER_BEARER_TOKEN", "")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def fetch(self, query: str, limit: int = 500) -> ConnectorResult:
        if not self.token:
            return self._empty(["TWITTER_BEARER_TOKEN not configured"])

        posts, accounts, errors = [], [], []
        # Exclude retweets for cleaner signal; include retweets=True for amplification
        safe_query = f"({query}) -is:retweet lang:sq OR lang:en OR lang:de"

        params = {
            "query": safe_query,
            "max_results": min(limit, 100),
            "tweet.fields": "created_at,author_id,text,entities,referenced_tweets",
            "user.fields": "created_at,public_metrics,profile_image_url,username,name",
            "expansions": "author_id,referenced_tweets.id",
        }

        fetched = 0
        next_token = None

        try:
            with httpx.Client(headers=self._headers(), timeout=15) as client:
                while fetched < limit:
                    if next_token:
                        params["next_token"] = next_token

                    r = client.get(f"{TWITTER_API}/tweets/search/recent",
                                   params=params)
                    if r.status_code == 429:
                        errors.append("Rate limit hit — partial results returned")
                        break
                    if r.status_code != 200:
                        errors.append(f"API error {r.status_code}: {r.text[:200]}")
                        break

                    data = r.json()
                    tweets = data.get("data", [])
                    users  = {u["id"]: u
                              for u in data.get("includes", {}).get("users", [])}

                    for tw in tweets:
                        uid  = tw["author_id"]
                        user = users.get(uid, {})
                        metrics = user.get("public_metrics", {})

                        # Amplification: referenced tweet author
                        amplifies = None
                        for ref in tw.get("referenced_tweets", []):
                            if ref.get("type") == "retweeted":
                                amplifies = ref.get("id")
                                break

                        posts.append(Post(
                            post_id=tw["id"],
                            account_id=uid,
                            timestamp=datetime.fromisoformat(
                                tw["created_at"].replace("Z", "+00:00")),
                            text=tw["text"],
                            hashtags=tuple(
                                h["tag"].lower()
                                for h in tw.get("entities", {}).get("hashtags", [])
                            ),
                            amplifies_account=amplifies,
                            is_sponsored=False,
                        ))

                        if uid not in {a.account_id for a in accounts}:
                            created_raw = user.get("created_at", "2020-01-01T00:00:00Z")
                            accounts.append(Account(
                                account_id=uid,
                                created_at=datetime.fromisoformat(
                                    created_raw.replace("Z", "+00:00")),
                                followers=metrics.get("followers_count", 0),
                                following=metrics.get("following_count", 0),
                                has_default_avatar=(
                                    "default_profile_image" in
                                    user.get("profile_image_url", "")
                                ),
                                display_name=user.get("name", ""),
                                handle=user.get("username", ""),
                            ))

                    fetched += len(tweets)
                    next_token = data.get("meta", {}).get("next_token")
                    if not next_token or len(tweets) == 0:
                        break

        except Exception as exc:
            errors.append(f"Fetch error: {exc}")

        return ConnectorResult(
            posts=posts, accounts=accounts, source=self.source_name,
            fetched_at=datetime.now(timezone.utc),
            total_fetched=fetched, errors=errors,
        )
