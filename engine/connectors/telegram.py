"""
Telegram connector — public channels via MTProto (Telethon).
Fetches messages from public channels/groups without login requirement
for public content.

Required env vars:
  TELEGRAM_API_ID    — from my.telegram.org
  TELEGRAM_API_HASH  — from my.telegram.org

Optional:
  TELEGRAM_SESSION   — session string (avoids re-auth)
"""
from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timezone
from typing import Optional

from coordination_engine import Post, Account
from .base import BaseConnector, ConnectorResult

try:
    from telethon import TelegramClient
    from telethon.tl.types import User, Channel
    from telethon.sessions import StringSession
    _TELETHON = True
except ImportError:
    _TELETHON = False

_HASHTAG_RE = re.compile(r"#(\w+)")


class TelegramConnector(BaseConnector):
    source_name = "telegram"

    def __init__(self,
                 api_id: Optional[int] = None,
                 api_hash: Optional[str] = None,
                 session_string: Optional[str] = None):
        self.api_id      = api_id or int(os.getenv("TELEGRAM_API_ID", "0"))
        self.api_hash    = api_hash or os.getenv("TELEGRAM_API_HASH", "")
        self.session_str = session_string or os.getenv("TELEGRAM_SESSION", "")

    def fetch(self, query: str, limit: int = 500) -> ConnectorResult:
        """
        query: comma-separated list of public channel usernames or t.me links.
        e.g. "gazetamapo,panorama_al,top_channel_al"
        """
        if not _TELETHON:
            return self._empty(["telethon not installed — pip install telethon"])
        if not self.api_id or not self.api_hash:
            return self._empty(["TELEGRAM_API_ID / TELEGRAM_API_HASH not configured"])

        try:
            return asyncio.get_event_loop().run_until_complete(
                self._async_fetch(query, limit))
        except RuntimeError:
            # New event loop needed in some environments
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(self._async_fetch(query, limit))

    async def _async_fetch(self, query: str, limit: int) -> ConnectorResult:
        channels = [c.strip().lstrip("@").replace("https://t.me/", "")
                    for c in query.split(",") if c.strip()]

        session = StringSession(self.session_str) if self.session_str else StringSession()
        posts, accounts, errors = [], [], []
        account_ids_seen: set[str] = set()

        async with TelegramClient(session, self.api_id, self.api_hash) as client:
            per_channel = max(10, limit // max(len(channels), 1))

            for channel in channels:
                try:
                    entity = await client.get_entity(channel)
                    channel_id = str(entity.id)

                    async for msg in client.iter_messages(entity,
                                                          limit=per_channel):
                        if not msg.text:
                            continue

                        sender_id = str(msg.sender_id or channel_id)
                        hashtags  = tuple(
                            h.lower() for h in _HASHTAG_RE.findall(msg.text))

                        # Forward = amplification
                        amplifies = None
                        if msg.fwd_from and msg.fwd_from.from_id:
                            fwd = msg.fwd_from.from_id
                            amplifies = str(getattr(fwd, "channel_id",
                                           getattr(fwd, "user_id", None)))

                        posts.append(Post(
                            post_id=f"tg_{channel_id}_{msg.id}",
                            account_id=sender_id,
                            timestamp=msg.date.astimezone(timezone.utc),
                            text=msg.text,
                            hashtags=hashtags,
                            amplifies_account=amplifies,
                            is_sponsored=False,
                        ))

                        if sender_id not in account_ids_seen:
                            account_ids_seen.add(sender_id)
                            sender = msg.sender
                            if isinstance(sender, (User, Channel)):
                                followers = getattr(
                                    getattr(sender, "participants_count", None),
                                    "__index__", lambda: 0)()
                                accounts.append(Account(
                                    account_id=sender_id,
                                    created_at=datetime.now(timezone.utc),
                                    followers=followers,
                                    following=0,
                                    has_default_avatar=False,
                                    display_name=getattr(sender, "title",
                                                  getattr(sender, "first_name", "")),
                                    handle=getattr(sender, "username", "") or "",
                                ))

                except Exception as exc:
                    errors.append(f"Channel {channel}: {exc}")

        return ConnectorResult(
            posts=posts, accounts=accounts, source=self.source_name,
            fetched_at=datetime.now(timezone.utc),
            total_fetched=len(posts), errors=errors,
        )
