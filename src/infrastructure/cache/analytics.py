"""
Redis を使用した AnalyticsCache 実装。
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from redis import Redis

from application.services.analytics import AnalyticsCache


@dataclass
class RedisAnalyticsCache(AnalyticsCache):
    redis: Redis
    namespace: str = "analytics_cache"

    def get(self, key: str) -> dict[str, object] | None:
        raw = self.redis.get(self._full_key(key))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def set(self, key: str, payload: dict[str, object], ttl_seconds: int) -> None:
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        self.redis.setex(self._full_key(key), ttl_seconds, serialized)

    def _full_key(self, key: str) -> str:
        return f"{self.namespace}:{key}"

