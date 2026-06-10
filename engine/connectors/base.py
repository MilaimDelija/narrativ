"""
Base connector interface — all input sources implement this.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from coordination_engine import Post, Account


@dataclass
class ConnectorResult:
    posts: list[Post]
    accounts: list[Account]
    source: str
    fetched_at: datetime
    total_fetched: int
    errors: list[str]


class BaseConnector(ABC):
    source_name: str = "unknown"

    @abstractmethod
    def fetch(self, query: str, limit: int = 500) -> ConnectorResult:
        """Fetch posts and accounts for a given query/topic."""
        ...

    def _empty(self, errors: list[str]) -> ConnectorResult:
        return ConnectorResult(
            posts=[], accounts=[], source=self.source_name,
            fetched_at=datetime.utcnow(), total_fetched=0, errors=errors,
        )
