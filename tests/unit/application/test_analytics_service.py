from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping, Sequence

from application.services.analytics import AnalyticsCache, AnalyticsRepository, AnalyticsService, MetricsPayload, MetricsQuery


class _FakeRepository(AnalyticsRepository):
    def __init__(self) -> None:
        self.calls: list[tuple[str, MetricsQuery]] = []
        self.data: Sequence[Mapping[str, float]] = [{"metric": "sharpe", "value": 1.5}]

    def _record(self, category: str, query: MetricsQuery) -> Sequence[Mapping[str, float]]:
        self.calls.append((category, query))
        return self.data

    def fetch_model_metrics(self, query: MetricsQuery) -> Sequence[Mapping[str, float]]:
        return self._record("model", query)

    def fetch_trading_metrics(self, query: MetricsQuery) -> Sequence[Mapping[str, float]]:
        return self._record("trading", query)

    def fetch_data_quality_metrics(self, query: MetricsQuery) -> Sequence[Mapping[str, float]]:
        return self._record("data_quality", query)

    def fetch_risk_metrics(self, query: MetricsQuery) -> Sequence[Mapping[str, float]]:
        return self._record("risk", query)


class _FakeCache(AnalyticsCache):
    def __init__(self) -> None:
        self.storage: dict[str, Mapping[str, object]] = {}

    def get(self, key: str) -> Mapping[str, object] | None:
        return self.storage.get(key)

    def set(self, key: str, payload: Mapping[str, object], ttl_seconds: int) -> None:  # noqa: ARG002
        self.storage[key] = payload


def test_service_returns_payload_and_caches() -> None:
    repo = _FakeRepository()
    cache = _FakeCache()
    service = AnalyticsService(repo, cache=cache, cache_ttl_seconds=120)

    query = MetricsQuery()
    result = service.get_model_metrics(query)

    assert isinstance(result, MetricsPayload)
    assert result.data[0]["metric"] == "sharpe"
    assert len(repo.calls) == 1

    cached = service.get_model_metrics(query)
    assert cached.data == result.data
    assert len(repo.calls) == 1  # cached response re-used


def test_generate_report_combines_metrics() -> None:
    repo = _FakeRepository()
    service = AnalyticsService(repo, cache=None)

    payload = service.generate_report("custom", MetricsQuery())

    metric_names = {row["metric"] for row in payload.data}
    assert "sharpe" in metric_names
    assert payload.meta["report_type"] == "custom"

