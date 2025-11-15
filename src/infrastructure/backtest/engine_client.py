"""
HTTP ベースの backtest-assets-engine クライアント実装。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

import httpx

from application.services.backtester import BacktestEngineClient, StressScenario
from domain import ModelArtifact


class BacktestEngineError(RuntimeError):
    """バックテストエンジン通信時の例外。"""


@dataclass(frozen=True)
class BacktestEngineSettings:
    """バックテストエンジンとの接続設定。"""

    base_url: str
    api_token: str | None
    timeout_seconds: float
    run_timeout_seconds: float
    verify_ssl: bool = True
    max_retries: int = 0
    retry_backoff_seconds: float = 1.0

    @staticmethod
    def from_mapping(mapping: Mapping[str, object]) -> "BacktestEngineSettings":
        def _require_str(key: str) -> str:
            value = mapping.get(key)
            if not isinstance(value, str) or not value:
                raise BacktestEngineError(f"backtest_engine.{key} は必須の文字列です。")
            return value

        def _require_float(key: str, default: float | None = None) -> float:
            value = mapping.get(key, default)
            if value is None:
                raise BacktestEngineError(f"backtest_engine.{key} が設定されていません。")
            try:
                return float(value)
            except (TypeError, ValueError) as exc:
                raise BacktestEngineError(f"backtest_engine.{key} は数値である必要があります。") from exc

        base_url = _require_str("base_url")
        api_token = mapping.get("api_token")
        if api_token is not None and not isinstance(api_token, str):
            raise BacktestEngineError("backtest_engine.api_token は文字列である必要があります。")

        verify_ssl = bool(mapping.get("verify_ssl", True))
        max_retries = int(mapping.get("max_retries", 0))
        retry_backoff = float(mapping.get("retry_backoff_seconds", 1.0))

        return BacktestEngineSettings(
            base_url=base_url.rstrip("/"),
            api_token=api_token,
            timeout_seconds=_require_float("timeout_seconds"),
            run_timeout_seconds=_require_float("run_timeout_seconds"),
            verify_ssl=verify_ssl,
            max_retries=max(0, max_retries),
            retry_backoff_seconds=max(0.0, retry_backoff),
        )


class BacktestEngineHttpClient(BacktestEngineClient):
    """
    backtest-assets-engine の HTTP API を叩く BacktestEngineClient 実装。
    """

    def __init__(
        self,
        settings: BacktestEngineSettings,
        *,
        client_factory: Callable[[BacktestEngineSettings], httpx.Client] | None = None,
    ) -> None:
        self._settings = settings
        self._client_factory = client_factory or self._default_client_factory

    def run(
        self,
        *,
        model_artifact: ModelArtifact,
        params: Mapping[str, float],
        config: Mapping[str, str],
        stress_scenarios: Sequence[StressScenario],
    ) -> Mapping[str, object]:
        payload = self._build_payload(model_artifact, params, config, stress_scenarios)
        attempt = 0
        last_error: Exception | None = None

        while attempt <= self._settings.max_retries:
            attempt += 1
            try:
                with self._client_factory(self._settings) as client:
                    response = client.post(
                        "/bt/run",
                        json=payload,
                        timeout=self._settings.timeout_seconds,
                    )
                    response.raise_for_status()
                    data = response.json()
                    if not isinstance(data, Mapping):
                        raise BacktestEngineError("バックテストAPI応答が不正です。Mapping を期待しました。")
                    return data
            except httpx.HTTPError as exc:  # pragma: no cover - ネットワーク異常
                last_error = exc
            except json.JSONDecodeError as exc:
                last_error = exc

            if attempt <= self._settings.max_retries:
                time.sleep(self._settings.retry_backoff_seconds)

        raise BacktestEngineError("バックテストAPI呼び出しに失敗しました。") from last_error

    def _build_payload(
        self,
        artifact: ModelArtifact,
        params: Mapping[str, float],
        config: Mapping[str, str],
        stress_scenarios: Sequence[StressScenario],
    ) -> Mapping[str, object]:
        return {
            "model": {
                "version": artifact.model_version,
                "ai1_path": str(artifact.ai1_path),
                "ai2_path": str(artifact.ai2_path),
                "feature_schema_path": str(artifact.feature_schema_path),
                "params_path": str(artifact.params_path),
                "metrics_path": str(artifact.metrics_path),
                "code_hash": artifact.code_hash,
                "data_hash": artifact.data_hash,
            },
            "params": dict(params),
            "engine_config": dict(config),
            "stress_scenarios": [
                {"name": scenario.name, "parameters": dict(scenario.parameters)} for scenario in stress_scenarios
            ],
        }

    def _default_client_factory(self, settings: BacktestEngineSettings) -> httpx.Client:
        headers = {}
        if settings.api_token:
            headers["Authorization"] = f"Bearer {settings.api_token}"
        return httpx.Client(
            base_url=settings.base_url,
            headers=headers,
            timeout=settings.timeout_seconds,
            verify=settings.verify_ssl,
        )

