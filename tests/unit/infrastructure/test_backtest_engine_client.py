from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

import httpx
import pytest

from domain import ModelArtifact
from infrastructure.backtest import BacktestEngineHttpClient, BacktestEngineSettings
from application.services.backtester import StressScenario


def make_artifact(tmp_path: Path) -> ModelArtifact:
    path = tmp_path / "artifact"
    path.mkdir()
    model_file = path / "ai1.bin"
    model_file.write_bytes(b"test")
    return ModelArtifact(
        model_version="model-001",
        created_at=datetime.now(timezone.utc),
        created_by="tests",
        ai1_path=model_file,
        ai2_path=model_file,
        feature_schema_path=path / "schema.json",
        params_path=path / "params.yaml",
        metrics_path=path / "metrics.json",
        code_hash="code-hash",
        data_hash="data-hash",
    )


def make_settings(base_url: str) -> BacktestEngineSettings:
    return BacktestEngineSettings(
        base_url=base_url,
        api_token="token",
        timeout_seconds=5,
        run_timeout_seconds=60,
        verify_ssl=False,
    )


def test_backtest_engine_client_sends_payload(tmp_path: Path) -> None:
    payload_holder: dict[str, Mapping[str, object]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        payload_holder["body"] = json.loads(request.content.decode())
        return httpx.Response(
            status_code=200,
            json={"summary": {"sharpe": 1.3}, "stress": {}},
        )

    transport = httpx.MockTransport(handler)

    def client_factory(settings: BacktestEngineSettings) -> httpx.Client:
        return httpx.Client(base_url=settings.base_url, transport=transport)

    client = BacktestEngineHttpClient(make_settings("https://example.com"), client_factory=client_factory)
    artifact = make_artifact(tmp_path)
    result = client.run(
        model_artifact=artifact,
        params={"theta1": 0.7},
        config={"timeframe": "1h"},
        stress_scenarios=[StressScenario(name="vol_spike", parameters={"value": 1.5})],
    )

    assert result["summary"]["sharpe"] == pytest.approx(1.3)
    body = payload_holder["body"]
    assert body["model"]["version"] == "model-001"
    assert body["params"]["theta1"] == 0.7
    assert body["stress_scenarios"][0]["name"] == "vol_spike"


def test_backtest_engine_client_raises_on_http_error(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(status_code=500, json={"detail": "error"})

    transport = httpx.MockTransport(handler)

    def client_factory(settings: BacktestEngineSettings) -> httpx.Client:
        return httpx.Client(base_url=settings.base_url, transport=transport)

    client = BacktestEngineHttpClient(make_settings("https://example.com"), client_factory=client_factory)

    artifact = make_artifact(tmp_path)
    with pytest.raises(Exception):
        client.run(
            model_artifact=artifact,
            params={},
            config={},
            stress_scenarios=[],
        )

