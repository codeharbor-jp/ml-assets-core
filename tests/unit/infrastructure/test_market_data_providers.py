from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

import httpx
import pytest

from infrastructure.adapters.market_data_provider import (
    FailoverMarketDataProvider,
    ProviderEntry,
    MarketDataProviderError,
    MarketDataProviderFactory,
    MarketDataRequest,
    MarketDataResponse,
    ProviderFailure,
    ProviderMetadata,
    ProviderStatus,
    SecondaryRestHttpClient,
    TwelveDataHttpClient,
)


class _StubProvider:
    def __init__(self, response: MarketDataResponse | Exception) -> None:
        self._response = response
        self.calls = 0

    def fetch(self, request: MarketDataRequest) -> MarketDataResponse:
        self.calls += 1
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def test_failover_market_data_provider_uses_secondary_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    request = MarketDataRequest(symbols=["EURUSD"], timeframe="1h", start_at="2024-01-01", end_at="2024-01-02")
    failure_metadata = ProviderMetadata(provider_name="primary", latency_ms=1.0)
    failure = ProviderFailure(status=ProviderStatus.FAILURE, message="primary failed", metadata=failure_metadata)
    failure_response = MarketDataResponse(
        status=ProviderStatus.FAILURE,
        candles=(),
        metadata=failure_metadata,
        failure=failure,
    )
    primary = _StubProvider(failure_response)

    success_metadata = ProviderMetadata(provider_name="secondary", latency_ms=2.0)
    success_response = MarketDataResponse(
        status=ProviderStatus.OK,
        candles=({"symbol": "EURUSD", "timestamp": "2024-01-01T00:00:00Z", "open": 1.0},),
        metadata=success_metadata,
    )
    secondary = _StubProvider(success_response)

    provider = FailoverMarketDataProvider(
        [
            ProviderEntry(name="primary", provider=primary),  # type: ignore[arg-type]
            ProviderEntry(name="secondary", provider=secondary),  # type: ignore[arg-type]
        ],
        max_attempts=1,
        backoff_seconds=0.0,
    )

    result = provider.fetch(request)

    assert result.status is ProviderStatus.OK
    assert result.metadata.provider_name == "secondary"
    assert primary.calls == 1
    assert secondary.calls == 1


def test_failover_market_data_provider_raises_after_all_attempts() -> None:
    request = MarketDataRequest(symbols=["EURUSD"], timeframe="1h", start_at="2024-01-01", end_at="2024-01-02")
    error = MarketDataResponse(
        status=ProviderStatus.FAILURE,
        candles=(),
        metadata=ProviderMetadata(provider_name="primary", latency_ms=1.0),
        failure=ProviderFailure(status=ProviderStatus.FAILURE, message="boom"),
    )
    provider = FailoverMarketDataProvider(
        [ProviderEntry(name="primary", provider=_StubProvider(error))],  # type: ignore[arg-type]
        max_attempts=2,
        backoff_seconds=0.0,
    )

    with pytest.raises(MarketDataProviderError):
        provider.fetch(request)


def test_twelvedata_http_client_parses_response(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "values": [
            {"datetime": "2024-01-01T00:00:00Z", "open": "1.0", "high": "1.1", "low": "0.9", "close": "1.05", "volume": "1000"},
        ]
    }

    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.headers: dict[str, str] = {}

        def json(self) -> Mapping[str, object]:
            return payload

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: _FakeResponse())

    client = TwelveDataHttpClient(
        base_url="https://api.example.com",
        api_key="dummy",
        timeout_seconds=5.0,
        max_retries=1,
        retry_backoff_seconds=0.0,
    )

    candles = client.fetch_candles(
        symbol="EURUSD",
        interval="1h",
        start_at="2024-01-01T00:00:00Z",
        end_at="2024-01-01T01:00:00Z",
    )

    assert len(candles) == 1
    candle = candles[0]
    assert candle["symbol"] == "EURUSD"
    assert math.isclose(float(candle["open"]), 1.0)
    assert candle["timestamp"] == "2024-01-01T00:00:00Z"


def test_secondary_rest_http_client_raises_on_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeResponse:
        def __init__(self) -> None:
            self.status_code = 429
            self.headers: dict[str, str] = {}

        def json(self) -> Mapping[str, object]:
            return {}

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: _FakeResponse())

    client = SecondaryRestHttpClient(
        base_url="https://secondary.example.com",
        auth_token=None,
        timeout_seconds=5.0,
        max_retries=1,
        retry_backoff_seconds=0.0,
    )

    with pytest.raises(Exception) as exc_info:
        client.fetch_series(
            symbols=["EURUSD"],
            interval="1h",
            start_at="2024-01-01T00:00:00Z",
            end_at="2024-01-01T01:00:00Z",
        )

    assert "レートリミット" in str(exc_info.value)


def test_market_data_provider_factory_builds_failover(monkeypatch: pytest.MonkeyPatch) -> None:
    raw_config = {
        "sources": {
            "providers": [
                {
                    "name": "twelvedata",
                    "type": "twelvedata",
                    "priority": 1,
                    "enabled": True,
                    "settings": {
                        "base_url": "https://api.example.com",
                        "api_key": "$TWELVE_TOKEN",
                        "timeout_seconds": 5.0,
                        "max_retries": 1,
                        "retry_backoff_seconds": 0.0,
                    },
                },
                {
                    "name": "secondary",
                    "type": "secondary_rest",
                    "priority": 2,
                    "enabled": True,
                    "settings": {
                        "base_url": "https://secondary.example.com",
                        "auth_token": "$SECONDARY_TOKEN",
                        "timeout_seconds": 5.0,
                        "max_retries": 1,
                        "retry_backoff_seconds": 0.0,
                    },
                },
            ],
            "failover": {"max_attempts": 2, "backoff_seconds": 0.0},
        }
    }

    @dataclass
    class _StubRepository:
        expected_env: str

        def load(self, name: str, *, environment: str) -> Mapping[str, object]:
            assert name == "sources"
            assert environment == self.expected_env
            return raw_config

    monkeypatch.setenv("TWELVE_TOKEN", "twelve-secret")
    monkeypatch.setenv("SECONDARY_TOKEN", "secondary-secret")

    factory = MarketDataProviderFactory(_StubRepository(expected_env="dev"), environment="dev")
    provider = factory.build()

    assert isinstance(provider, FailoverMarketDataProvider)


