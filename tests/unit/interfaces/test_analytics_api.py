from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping, Sequence
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from application.services.analytics import AnalyticsService, MetricsPayload, MetricsQuery
from interfaces.api import create_api_app
from interfaces.api.deps import ApiDependencies, configure_dependencies


class _StubAnalyticsService(AnalyticsService):
    def __init__(self) -> None:  # type: ignore[super-init-not-called]
        self.payload = MetricsPayload(
            generated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            data=[{"metric": "sharpe", "value": 1.23}],
            meta={"category": "model"},
        )

    def get_model_metrics(self, query: MetricsQuery) -> MetricsPayload:  # noqa: ARG002
        return self.payload

    def get_trading_metrics(self, query: MetricsQuery) -> MetricsPayload:  # noqa: ARG002
        return self.payload

    def get_data_quality_metrics(self, query: MetricsQuery) -> MetricsPayload:  # noqa: ARG002
        return self.payload

    def get_risk_metrics(self, query: MetricsQuery) -> MetricsPayload:  # noqa: ARG002
        return self.payload

    def generate_report(self, report_type: str, query: MetricsQuery) -> MetricsPayload:  # noqa: ARG002
        return MetricsPayload(
            generated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            data=[{"metric": "report", "value": 42.0}],
            meta={"report_type": report_type},
        )


def _configure_stub_dependencies() -> None:
    analytics_service = _StubAnalyticsService()
    deps = ApiDependencies(
        learning_usecase=MagicMock(),
        inference_usecase=MagicMock(),
        publish_usecase=MagicMock(),
        ops_usecase=MagicMock(),
        config_usecase=MagicMock(),
        trainer_service=MagicMock(),
        backtester_service=MagicMock(),
        theta_optimizer=MagicMock(),
        catalog_builder=MagicMock(),
        analytics_service=analytics_service,
    )
    configure_dependencies(deps)


def test_get_model_metrics_endpoint_returns_payload() -> None:
    _configure_stub_dependencies()
    app = create_api_app()
    client = TestClient(app)

    response = client.get("/api/v1/metrics/model")

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["category"] == "model"
    assert body["data"][0]["metric"] == "sharpe"


def test_generate_report_endpoint() -> None:
    _configure_stub_dependencies()
    app = create_api_app()
    client = TestClient(app)

    response = client.post("/api/v1/reports/generate", json={"report_type": "combined"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["report_type"] == "combined"
    assert payload["data"][0]["metric"] == "report"

