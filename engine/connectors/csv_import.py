"""
CSV import connector — universal input for any exported dataset.

Expected columns (flexible — maps common variants):
  post_id / id
  account_id / user_id / author_id
  timestamp / created_at / date / time
  text / content / message / body
  hashtags / tags          (optional, comma-separated)
  amplifies_account / repost_of / retweeted_from  (optional)
  is_sponsored / sponsored / paid   (optional, bool)

  followers / follower_count        (optional account field)
  following / following_count       (optional account field)
  account_created / user_created    (optional account field)
  display_name / name / full_name   (optional account field)
  handle / username / screen_name   (optional account field)
"""
from __future__ import annotations

import csv
import hashlib
import io
from datetime import datetime, timezone
from typing import Optional, Union

from coordination_engine import Post, Account
from .base import BaseConnector, ConnectorResult

# Column name aliases — maps common variants to canonical names
_POST_ALIASES = {
    "post_id":   ["post_id", "id", "tweet_id", "message_id", "status_id"],
    "account_id":["account_id", "user_id", "author_id", "sender_id", "from_id"],
    "timestamp": ["timestamp", "created_at", "date", "time", "posted_at", "datetime"],
    "text":      ["text", "content", "message", "body", "tweet", "post_text"],
    "hashtags":  ["hashtags", "tags", "hash_tags"],
    "amplifies": ["amplifies_account", "repost_of", "retweeted_from",
                  "forwarded_from", "shared_from"],
    "sponsored": ["is_sponsored", "sponsored", "paid", "promoted"],
}

_ACCOUNT_ALIASES = {
    "followers":  ["followers", "follower_count", "followers_count"],
    "following":  ["following", "following_count", "friends_count"],
    "created_at": ["account_created", "user_created", "account_created_at",
                   "member_since"],
    "display_name":["display_name", "name", "full_name", "real_name"],
    "handle":     ["handle", "username", "screen_name", "user_handle"],
    "default_avatar":["has_default_avatar", "default_avatar", "no_avatar"],
}


def _find(row: dict, aliases: list[str], default="") -> str:
    for alias in aliases:
        if alias in row and row[alias] not in ("", None):
            return str(row[alias]).strip()
    return default


def _parse_ts(s: str) -> datetime:
    """Try several datetime formats."""
    formats = [
        "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%SZ",  "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",      "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",   "%d/%m/%Y",
        "%m/%d/%Y %H:%M:%S",   "%m/%d/%Y",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(s.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return datetime.now(timezone.utc)


def _stable_id(value: str, prefix: str = "row") -> str:
    return prefix + "_" + hashlib.sha256(value.encode()).hexdigest()[:10]


def _parse_hashtags(raw: str) -> tuple:
    if not raw:
        return ()
    return tuple(
        t.strip().lstrip("#").lower()
        for t in raw.replace(";", ",").split(",")
        if t.strip()
    )


def _parse_bool(s: str) -> bool:
    return s.strip().lower() in ("1", "true", "yes", "y", "t")


class CSVConnector(BaseConnector):
    source_name = "csv"

    def fetch(self, query: str, limit: int = 10000) -> ConnectorResult:
        """query = file path to CSV file."""
        try:
            with open(query, encoding="utf-8-sig", errors="replace") as f:
                return self._parse(f.read(), limit)
        except FileNotFoundError:
            return self._empty([f"File not found: {query}"])
        except Exception as exc:
            return self._empty([f"CSV read error: {exc}"])

    def parse_string(self, csv_content: str, limit: int = 10000) -> ConnectorResult:
        """Parse CSV from a string (used by API upload endpoint)."""
        return self._parse(csv_content, limit)

    def _parse(self, content: str, limit: int) -> ConnectorResult:
        posts, errors = [], []
        accounts_map: dict[str, Account] = {}

        try:
            reader = csv.DictReader(io.StringIO(content))
            # Normalise column names to lowercase
            rows = [{k.lower().strip(): v for k, v in row.items()}
                    for row in reader]
        except Exception as exc:
            return self._empty([f"CSV parse error: {exc}"])

        if not rows:
            return self._empty(["CSV is empty"])

        for i, row in enumerate(rows[:limit]):
            try:
                # Post fields
                raw_id = _find(row, _POST_ALIASES["post_id"]) or str(i)
                post_id = _stable_id(raw_id + str(i), "csv")

                account_id = _find(row, _POST_ALIASES["account_id"])
                if not account_id:
                    errors.append(f"Row {i}: missing account_id — skipped")
                    continue

                raw_ts = _find(row, _POST_ALIASES["timestamp"])
                timestamp = _parse_ts(raw_ts) if raw_ts else datetime.now(timezone.utc)

                text = _find(row, _POST_ALIASES["text"])
                if not text:
                    continue  # skip empty posts silently

                hashtags  = _parse_hashtags(_find(row, _POST_ALIASES["hashtags"]))
                amplifies = _find(row, _POST_ALIASES["amplifies"]) or None
                sponsored = _parse_bool(_find(row, _POST_ALIASES["sponsored"]))

                posts.append(Post(
                    post_id=post_id,
                    account_id=account_id,
                    timestamp=timestamp,
                    text=text,
                    hashtags=hashtags,
                    amplifies_account=amplifies if amplifies else None,
                    is_sponsored=sponsored,
                ))

                # Account fields (best-effort from same row)
                if account_id not in accounts_map:
                    raw_created = _find(row, _ACCOUNT_ALIASES["created_at"])
                    created_at = _parse_ts(raw_created) if raw_created else \
                                 datetime(2020, 1, 1, tzinfo=timezone.utc)

                    try:
                        followers = int(float(
                            _find(row, _ACCOUNT_ALIASES["followers"]) or "0"))
                    except ValueError:
                        followers = 0
                    try:
                        following = int(float(
                            _find(row, _ACCOUNT_ALIASES["following"]) or "0"))
                    except ValueError:
                        following = 0

                    accounts_map[account_id] = Account(
                        account_id=account_id,
                        created_at=created_at,
                        followers=followers,
                        following=following,
                        has_default_avatar=_parse_bool(
                            _find(row, _ACCOUNT_ALIASES["default_avatar"])),
                        display_name=_find(row, _ACCOUNT_ALIASES["display_name"]),
                        handle=_find(row, _ACCOUNT_ALIASES["handle"]),
                    )

            except Exception as exc:
                errors.append(f"Row {i}: {exc}")

        return ConnectorResult(
            posts=posts,
            accounts=list(accounts_map.values()),
            source=self.source_name,
            fetched_at=datetime.now(timezone.utc),
            total_fetched=len(posts),
            errors=errors,
        )
