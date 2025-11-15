"""
Analytics API 向けの集計サービス。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Mapping, MutableMapping, Protocol, Sequence


@dataclass(frozen=True)
class MetricsQuery:
    """
    メトリクス取得時のフィルタ条件。
    """

    start: datetime | None = None
    end: datetime | None = None
    pair_id: str | None = None

    def cache_key(self) -> str:
        payload = {
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "pair_id": self.pair_id,
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MetricsPayload:
    """
    Analytics API のレスポンスとなるメトリクスデータ。
    """

    generated_at: datetime
    data: Sequence[Mapping[str, float]]
    meta: Mapping[str, str] = field(default_factory=dict)

    def to_mapping(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "data": [dict(item) for item in self.data],
            "meta": dict(self.meta),
        }

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> "MetricsPayload":
        generated = mapping.get("generated_at")
        if isinstance(generated, str):
            generated_at = datetime.fromisoformat(generated)
        elif isinstance(generated, datetime):
            generated_at = generated
        else:
            generated_at = datetime.now(timezone.utc)
        data = mapping.get("data", [])
        if isinstance(data, Sequence):
            converted = [dict(item) for item in data]  # type: ignore[arg-type]
        else:
            converted = []
        meta_raw = mapping.get("meta", {})
        meta = dict(meta_raw) if isinstance(meta_raw, Mapping) else {}
        return cls(generated_at=generated_at, data=converted, meta=meta)


class AnalyticsRepository(Protocol):
    """
    データソースからメトリクスを取得するリポジトリのプロトコル。
    """

    def fetch_model_metrics(self, query: MetricsQuery) -> Sequence[Mapping[str, float]]:
        ...

    def fetch_trading_metrics(self, query: MetricsQuery) -> Sequence[Mapping[str, float]]:
        ...

    def fetch_data_quality_metrics(self, query: MetricsQuery) -> Sequence[Mapping[str, float]]:
        ...

    def fetch_risk_metrics(self, query: MetricsQuery) -> Sequence[Mapping[str, float]]:
        ...


class AnalyticsCache(Protocol):
    """
    Analytics 結果のキャッシュインターフェース。
    """

    def get(self, key: str) -> Mapping[str, object] | None:
        ...

    def set(self, key: str, payload: Mapping[str, object], ttl_seconds: int) -> None:
        ...


class AnalyticsService:
    """
    Analytics API のユースケースを提供するサービス。
    """

    def __init__(
        self,
        repository: AnalyticsRepository,
        *,
        cache: AnalyticsCache | None = None,
        cache_ttl_seconds: int = 60,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._cache = cache
        self._cache_ttl = cache_ttl_seconds
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def get_model_metrics(self, query: MetricsQuery) -> MetricsPayload:
        return self._get_payload("model", query, self._repository.fetch_model_metrics)

    def get_trading_metrics(self, query: MetricsQuery) -> MetricsPayload:
        return self._get_payload("trading", query, self._repository.fetch_trading_metrics)

    def get_data_quality_metrics(self, query: MetricsQuery) -> MetricsPayload:
        return self._get_payload("data_quality", query, self._repository.fetch_data_quality_metrics)

    def get_risk_metrics(self, query: MetricsQuery) -> MetricsPayload:
        return self._get_payload("risk", query, self._repository.fetch_risk_metrics)

    def generate_report(self, report_type: str, query: MetricsQuery) -> MetricsPayload:
        """
        シンプルなレポート生成。現状は指定タイプに応じてメトリクスを合成する。
        """

        if report_type == "model":
            return self.get_model_metrics(query)
        if report_type == "trading":
            return self.get_trading_metrics(query)
        if report_type == "data_quality":
            return self.get_data_quality_metrics(query)
        if report_type == "risk":
            return self.get_risk_metrics(query)

        combined: MutableMapping[str, float] = {}
        for payload in (
            self.get_model_metrics(query),
            self.get_trading_metrics(query),
            self.get_data_quality_metrics(query),
            self.get_risk_metrics(query),
        ):
            for row in payload.data:
                combined.update({f"{row.get('metric', 'metric')}": row.get("value", 0.0)})
        generated_at = self._clock()
        meta = {"report_type": report_type or "combined"}
        data = [dict(metric=key, value=value) for key, value in combined.items()]
        return MetricsPayload(generated_at=generated_at, data=data, meta=meta)

    def _get_payload(
        self,
        category: str,
        query: MetricsQuery,
        fetcher: Callable[[MetricsQuery], Sequence[Mapping[str, float]]],
    ) -> MetricsPayload:
        cache_key = f"{category}:{query.cache_key()}"
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return MetricsPayload.from_mapping(cached)

        data = fetcher(query)
        payload = MetricsPayload(
            generated_at=self._clock(),
            data=data,
            meta=self._build_meta(category, query),
        )
        if self._cache:
            self._cache.set(cache_key, payload.to_mapping(), self._cache_ttl)
        return payload

    @staticmethod
    def _build_meta(category: str, query: MetricsQuery) -> Mapping[str, str]:
        meta: dict[str, str] = {"category": category}
        if query.start:
            meta["from"] = query.start.isoformat()
        if query.end:
            meta["to"] = query.end.isoformat()
        if query.pair_id:
            meta["pair_id"] = query.pair_id
        return meta

