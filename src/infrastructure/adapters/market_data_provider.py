"""
市場データ取得アダプタの抽象定義。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol, Sequence

import httpx

from ..configs import ConfigRepository


class ProviderStatus(str, Enum):
    """データ取得の結果ステータス。"""

    OK = "ok"
    RATE_LIMIT = "rate_limit"
    FAILURE = "failure"
    STALE = "stale"


@dataclass(frozen=True)
class ProviderMetadata:
    """取得時のメタデータ。"""

    provider_name: str
    latency_ms: float
    rate_limit_remaining: int | None = None
    additional: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderFailure:
    """失敗時の情報。"""

    status: ProviderStatus
    message: str
    metadata: ProviderMetadata | None = None


class MarketDataProviderError(RuntimeError):
    """マーケットデータ取得がすべてのプロバイダで失敗した場合の例外。"""


class MarketDataClientError(RuntimeError):
    """市場データクライアントでのエラーの基底例外。"""


class MarketDataRateLimitError(MarketDataClientError):
    """レートリミットに到達した場合の例外。"""


@dataclass(frozen=True)
class MarketDataRequest:
    """市場データ取得リクエスト。"""

    symbols: Sequence[str]
    timeframe: str
    start_at: str
    end_at: str
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.symbols:
            raise ValueError("symbols は1件以上指定してください。")
        if not self.timeframe:
            raise ValueError("timeframe は必須です。")
        if not self.start_at or not self.end_at:
            raise ValueError("start_at と end_at は必須です。")


@dataclass(frozen=True)
class MarketDataResponse:
    """市場データ取得の応答。"""

    status: ProviderStatus
    candles: Sequence[Mapping[str, float | str]]
    metadata: ProviderMetadata
    failure: ProviderFailure | None = None

    def __post_init__(self) -> None:
        if self.status == ProviderStatus.OK and not self.candles:
            raise ValueError("status=OK の場合、candles を空にはできません。")
        if self.status != ProviderStatus.OK and self.failure is None:
            raise ValueError("status!=OK の場合、failure を設定してください。")


class MarketDataProvider(Protocol):
    """
    市場データ提供者の共通インターフェース。
    """

    def fetch(self, request: MarketDataRequest) -> MarketDataResponse:
        ...


class TwelveDataClient(Protocol):
    """
    TwelveData API へのクライアント。
    """

    def fetch_candles(
        self,
        *,
        symbol: str,
        interval: str,
        start_at: str,
        end_at: str,
    ) -> Sequence[Mapping[str, float | str]]:
        ...


class TwelveDataAdapter(MarketDataProvider):
    """
    TwelveData クライアントを利用して MarketDataProvider を実装するアダプタ。
    """

    def __init__(self, client: TwelveDataClient, provider_name: str = "twelvedata") -> None:
        self._client = client
        self._provider_name = provider_name

    def fetch(self, request: MarketDataRequest) -> MarketDataResponse:
        started_at = time.perf_counter()
        try:
            candles: list[Mapping[str, float | str]] = []
            for symbol in request.symbols:
                data = self._client.fetch_candles(
                    symbol=symbol,
                    interval=request.timeframe,
                    start_at=request.start_at,
                    end_at=request.end_at,
                )
                candles.extend(_normalize_candles(data, default_symbol=symbol))
        except MarketDataRateLimitError as exc:
            return _build_failure_response(
                provider_name=self._provider_name,
                status=ProviderStatus.RATE_LIMIT,
                message=str(exc),
                started_at=started_at,
            )
        except MarketDataClientError as exc:
            return _build_failure_response(
                provider_name=self._provider_name,
                status=ProviderStatus.FAILURE,
                message=str(exc),
                started_at=started_at,
            )
        except Exception as exc:  # pragma: no cover - 予期せぬ例外のフェイルセーフ
            return _build_failure_response(
                provider_name=self._provider_name,
                status=ProviderStatus.FAILURE,
                message=str(exc),
                started_at=started_at,
            )

        latency_ms = (time.perf_counter() - started_at) * 1000.0
        metadata = ProviderMetadata(
            provider_name=self._provider_name,
            latency_ms=latency_ms,
        )
        return MarketDataResponse(
            status=ProviderStatus.OK,
            candles=tuple(candles),
            metadata=metadata,
        )

    @property
    def name(self) -> str:
        return self._provider_name


class SecondaryRestClient(Protocol):
    """
    セカンダリ REST データソースへのクライアント。
    """

    def fetch_series(
        self,
        *,
        symbols: Sequence[str],
        interval: str,
        start_at: str,
        end_at: str,
    ) -> Sequence[Mapping[str, Any]]:
        ...


class SecondaryRestAdapter(MarketDataProvider):
    """
    セカンダリ REST API を利用した MarketDataProvider 実装。
    """

    def __init__(self, client: SecondaryRestClient, provider_name: str = "secondary_rest") -> None:
        self._client = client
        self._provider_name = provider_name

    def fetch(self, request: MarketDataRequest) -> MarketDataResponse:
        started_at = time.perf_counter()
        try:
            candles = _normalize_candles(
                self._client.fetch_series(
                    symbols=request.symbols,
                    interval=request.timeframe,
                    start_at=request.start_at,
                    end_at=request.end_at,
                )
            )
        except MarketDataRateLimitError as exc:
            return _build_failure_response(
                provider_name=self._provider_name,
                status=ProviderStatus.RATE_LIMIT,
                message=str(exc),
                started_at=started_at,
            )
        except MarketDataClientError as exc:
            return _build_failure_response(
                provider_name=self._provider_name,
                status=ProviderStatus.FAILURE,
                message=str(exc),
                started_at=started_at,
            )
        except Exception as exc:  # pragma: no cover - 予期せぬ例外のフェイルセーフ
            return _build_failure_response(
                provider_name=self._provider_name,
                status=ProviderStatus.FAILURE,
                message=str(exc),
                started_at=started_at,
            )

        latency_ms = (time.perf_counter() - started_at) * 1000.0
        metadata = ProviderMetadata(
            provider_name=self._provider_name,
            latency_ms=latency_ms,
        )
        return MarketDataResponse(
            status=ProviderStatus.OK,
            candles=candles,
            metadata=metadata,
        )

    @property
    def name(self) -> str:
        return self._provider_name


@dataclass(frozen=True)
class ProviderDefinition:
    """
    sources.yaml に定義された各プロバイダのメタデータ。
    """

    name: str
    type: str
    priority: int
    enabled: bool
    settings: Mapping[str, object]


@dataclass(frozen=True)
class FailoverPolicy:
    """
    フェイルオーバに関する設定。
    """

    max_attempts: int
    backoff_seconds: float


@dataclass(frozen=True)
class SourcesConfig:
    """
    マーケットデータソースに関する全体設定。
    """

    providers: tuple[ProviderDefinition, ...]
    failover: FailoverPolicy

    @staticmethod
    def from_mapping(data: Mapping[str, object]) -> "SourcesConfig":
        if "sources" not in data:
            raise ValueError("sources.yaml には 'sources' セクションが必須です。")

        sources_section = data["sources"]
        if not isinstance(sources_section, Mapping):
            raise ValueError("'sources' セクションは Mapping である必要があります。")

        providers_section = sources_section.get("providers")
        if not isinstance(providers_section, Sequence) or not providers_section:
            raise ValueError("'sources.providers' には1件以上のエントリが必要です。")

        provider_definitions: list[ProviderDefinition] = []
        for entry in providers_section:
            if not isinstance(entry, Mapping):
                raise ValueError("providers の各エントリは Mapping である必要があります。")
            name = _require_str(entry, "name")
            provider_type = _require_str(entry, "type")
            priority = _require_int(entry, "priority")
            enabled = bool(entry.get("enabled", True))
            settings_raw = entry.get("settings")
            if not isinstance(settings_raw, Mapping):
                raise ValueError(f"provider '{name}' の settings セクションが不正です。")
            provider_definitions.append(
                ProviderDefinition(
                    name=name,
                    type=provider_type,
                    priority=priority,
                    enabled=enabled,
                    settings=MappingProxyType(dict(settings_raw)),
                )
            )

        failover_section = sources_section.get("failover", {})
        if not isinstance(failover_section, Mapping):
            raise ValueError("'sources.failover' は Mapping である必要があります。")

        max_attempts = _require_int(failover_section, "max_attempts")
        backoff_seconds = _require_float(failover_section, "backoff_seconds")

        ordered_providers = tuple(sorted(provider_definitions, key=lambda item: item.priority))

        return SourcesConfig(
            providers=ordered_providers,
            failover=FailoverPolicy(
                max_attempts=max_attempts,
                backoff_seconds=backoff_seconds,
            ),
        )


def load_sources_config(config_repository: ConfigRepository, *, environment: str) -> SourcesConfig:
    """
    ConfigRepository から sources 設定を読み込み、SourcesConfig に変換する。
    """

    raw = config_repository.load("sources", environment=environment)
    return SourcesConfig.from_mapping(raw)


class TwelveDataHttpClient(TwelveDataClient):
    """
    TwelveData REST API へのシンプルな同期クライアント。
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float,
        max_retries: int,
        retry_backoff_seconds: float,
    ) -> None:
        if not base_url:
            raise ValueError("TwelveData base_url は必須です。")
        if not api_key:
            raise ValueError("TwelveData api_key は必須です。")
        if max_retries < 1:
            raise ValueError("max_retries は 1 以上である必要があります。")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds は正の値である必要があります。")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds は 0 以上である必要があります。")

        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds

    def fetch_candles(
        self,
        *,
        symbol: str,
        interval: str,
        start_at: str,
        end_at: str,
    ) -> Sequence[Mapping[str, float | str]]:
        last_error: Exception | None = None
        url = f"{self._base_url}/time_series"
        params = {
            "symbol": symbol,
            "interval": interval,
            "start_date": start_at,
            "end_date": end_at,
            "apikey": self._api_key,
            "format": "JSON",
        }

        for attempt in range(1, self._max_retries + 1):
            try:
                response = httpx.get(url, params=params, timeout=self._timeout_seconds)
                _raise_for_rate_limit(response, provider_name="twelvedata")
                response.raise_for_status()
                payload = response.json()
                values = payload.get("values")
                if not isinstance(values, Sequence):
                    raise MarketDataClientError("TwelveData レスポンスに 'values' セクションが存在しません。")
                return _normalize_candles(values, default_symbol=symbol)
            except MarketDataRateLimitError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt < self._max_retries:
                    time.sleep(self._retry_backoff_seconds)

        raise MarketDataClientError(f"TwelveData API の呼び出しに失敗しました: {last_error!s}") from last_error


class SecondaryRestHttpClient(SecondaryRestClient):
    """
    セカンダリ REST API への同期クライアント。
    """

    def __init__(
        self,
        *,
        base_url: str,
        auth_token: str | None,
        timeout_seconds: float,
        max_retries: int,
        retry_backoff_seconds: float,
    ) -> None:
        if not base_url:
            raise ValueError("Secondary REST base_url は必須です。")
        if max_retries < 1:
            raise ValueError("max_retries は 1 以上である必要があります。")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds は正の値である必要があります。")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds は 0 以上である必要があります。")

        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._headers: dict[str, str] = {}
        if auth_token:
            self._headers["Authorization"] = auth_token if auth_token.startswith("Bearer ") else f"Bearer {auth_token}"

    def fetch_series(
        self,
        *,
        symbols: Sequence[str],
        interval: str,
        start_at: str,
        end_at: str,
    ) -> Sequence[Mapping[str, Any]]:
        last_error: Exception | None = None
        url = f"{self._base_url}/candles"
        params = {
            "symbols": ",".join(symbols),
            "interval": interval,
            "start_at": start_at,
            "end_at": end_at,
        }

        for attempt in range(1, self._max_retries + 1):
            try:
                response = httpx.get(url, params=params, headers=self._headers, timeout=self._timeout_seconds)
                _raise_for_rate_limit(response, provider_name="secondary_rest")
                response.raise_for_status()
                payload = response.json()
                candles = payload.get("candles", payload)
                if not isinstance(candles, Sequence):
                    raise MarketDataClientError("Secondary REST レスポンスに 'candles' セクションが存在しません。")
                return candles
            except MarketDataRateLimitError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt < self._max_retries:
                    time.sleep(self._retry_backoff_seconds)

        raise MarketDataClientError(f"Secondary REST API の呼び出しに失敗しました: {last_error!s}") from last_error


@dataclass(frozen=True)
class ProviderEntry:
    """
    フェイルオーバ対象となるプロバイダのエントリ。
    """

    name: str
    provider: MarketDataProvider


class FailoverMarketDataProvider(MarketDataProvider):
    """
    複数プロバイダを順番に試行し、成功した結果を返す MarketDataProvider 実装。
    """

    def __init__(
        self,
        providers: Sequence[ProviderEntry],
        *,
        max_attempts: int,
        backoff_seconds: float,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        if not providers:
            raise ValueError("providers は 1 件以上必要です。")
        if max_attempts < 1:
            raise ValueError("max_attempts は 1 以上である必要があります。")
        if backoff_seconds < 0:
            raise ValueError("backoff_seconds は 0 以上である必要があります。")

        self._providers = tuple(providers)
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds
        self._sleep = sleep or time.sleep

    def fetch(self, request: MarketDataRequest) -> MarketDataResponse:
        failures: list[str] = []
        last_failure: ProviderFailure | None = None

        for attempt in range(1, self._max_attempts + 1):
            for entry in self._providers:
                try:
                    response = entry.provider.fetch(request)
                except Exception as exc:  # pragma: no cover - 予期せぬ例外のフェイルセーフ
                    metadata = ProviderMetadata(provider_name=entry.name, latency_ms=0.0)
                    last_failure = ProviderFailure(
                        status=ProviderStatus.FAILURE,
                        message=str(exc),
                        metadata=metadata,
                    )
                    failures.append(f"{entry.name}: {exc!s}")
                    continue

                if response.status == ProviderStatus.OK:
                    return response

                failure = response.failure or ProviderFailure(
                    status=response.status,
                    message=f"Provider {entry.name} returned status {response.status.value}",
                    metadata=response.metadata,
                )
                last_failure = failure
                failures.append(f"{entry.name}: {failure.message}")

            if attempt < self._max_attempts and self._backoff_seconds:
                self._sleep(self._backoff_seconds)

        details = "; ".join(failures) if failures else "no detailed failure information"
        message = (
            f"すべての MarketDataProvider が失敗しました "
            f"(attempts={self._max_attempts}, providers={len(self._providers)}): {details}"
        )
        raise MarketDataProviderError(message) from (
            None if last_failure is None else RuntimeError(last_failure.message)
        )


class MarketDataProviderFactory:
    """
    sources.yaml の設定からフェイルオーバ可能な MarketDataProvider を組み立てるファクトリ。
    """

    def __init__(self, config_repository: ConfigRepository, *, environment: str) -> None:
        self._config_repository = config_repository
        self._environment = environment

    def build(self) -> MarketDataProvider:
        sources_config = load_sources_config(self._config_repository, environment=self._environment)

        entries: list[ProviderEntry] = []
        for definition in sources_config.providers:
            if not definition.enabled:
                continue
            provider = self._create_provider(definition)
            entries.append(ProviderEntry(name=definition.name, provider=provider))

        if not entries:
            raise ValueError("有効化された MarketDataProvider が存在しません。sources.yaml を確認してください。")

        return FailoverMarketDataProvider(
            entries,
            max_attempts=sources_config.failover.max_attempts,
            backoff_seconds=sources_config.failover.backoff_seconds,
        )

    def _create_provider(self, definition: ProviderDefinition) -> MarketDataProvider:
        settings = definition.settings
        provider_type = definition.type.lower()

        if provider_type == "twelvedata":
            return TwelveDataAdapter(
                TwelveDataHttpClient(
                    base_url=_resolve_setting_str(settings, "base_url"),
                    api_key=_resolve_setting_str(settings, "api_key"),
                    timeout_seconds=_require_float(settings, "timeout_seconds"),
                    max_retries=_require_int(settings, "max_retries"),
                    retry_backoff_seconds=_require_float(settings, "retry_backoff_seconds"),
                ),
                provider_name=definition.name,
            )
        if provider_type == "secondary_rest":
            return SecondaryRestAdapter(
                SecondaryRestHttpClient(
                    base_url=_resolve_setting_str(settings, "base_url"),
                    auth_token=_resolve_setting_optional_str(settings, "auth_token"),
                    timeout_seconds=_require_float(settings, "timeout_seconds"),
                    max_retries=_require_int(settings, "max_retries"),
                    retry_backoff_seconds=_require_float(settings, "retry_backoff_seconds"),
                ),
                provider_name=definition.name,
            )

        raise ValueError(f"未知の provider.type '{definition.type}' が指定されました。")


def _build_failure_response(
    *,
    provider_name: str,
    status: ProviderStatus,
    message: str,
    started_at: float,
) -> MarketDataResponse:
    latency_ms = (time.perf_counter() - started_at) * 1000.0
    metadata = ProviderMetadata(provider_name=provider_name, latency_ms=latency_ms)
    failure = ProviderFailure(status=status, message=message, metadata=metadata)
    return MarketDataResponse(status=status, candles=(), metadata=metadata, failure=failure)


def _normalize_candles(
    data: Sequence[Mapping[str, Any]],
    *,
    default_symbol: str | None = None,
) -> tuple[Mapping[str, float | str], ...]:
    if not isinstance(data, Sequence):
        raise MarketDataClientError("キャンドルデータが配列ではありません。")

    normalized: list[Mapping[str, float | str]] = []
    for raw in data:
        if not isinstance(raw, Mapping):
            raise MarketDataClientError("キャンドルデータの要素がマッピングではありません。")

        symbol = raw.get("symbol", default_symbol)
        if symbol is None or symbol == "":
            raise MarketDataClientError("キャンドルデータに 'symbol' が含まれていません。")

        timestamp = raw.get("timestamp") or raw.get("datetime")
        if timestamp is None:
            raise MarketDataClientError("キャンドルデータに 'timestamp' または 'datetime' が含まれていません。")

        record: dict[str, float | str] = {
            "symbol": str(symbol),
            "timestamp": str(timestamp),
        }

        for key in ("open", "high", "low", "close", "volume"):
            if key in raw and raw[key] is not None:
                try:
                    record[key] = float(raw[key])
                except (TypeError, ValueError) as exc:
                    raise MarketDataClientError(f"キャンドルデータの '{key}' を float に変換できません。") from exc

        normalized.append(record)

    return tuple(normalized)


def _raise_for_rate_limit(response: httpx.Response, *, provider_name: str) -> None:
    if response.status_code == 429:
        remaining = response.headers.get("X-RateLimit-Remaining")
        message = f"{provider_name} のレートリミットに到達しました (status=429)"
        if remaining is not None:
            message += f" (remaining={remaining})"
        raise MarketDataRateLimitError(message)


def _require_str(mapping: Mapping[str, object], key: str) -> str:
    if key not in mapping:
        raise ValueError(f"設定キー '{key}' が定義されていません。")
    value = mapping[key]
    if not isinstance(value, str):
        raise ValueError(f"設定キー '{key}' は文字列である必要があります。")
    return value


def _require_int(mapping: Mapping[str, object], key: str) -> int:
    value = mapping.get(key)
    if value is None:
        raise ValueError(f"設定キー '{key}' が定義されていません。")
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"設定キー '{key}' は空文字列です。")
        try:
            return int(stripped)
        except ValueError as exc:
            raise ValueError(f"設定キー '{key}' は整数である必要があります。") from exc
    raise ValueError(f"設定キー '{key}' は整数である必要があります。")


def _require_float(mapping: Mapping[str, object], key: str) -> float:
    value = mapping.get(key)
    if value is None:
        raise ValueError(f"設定キー '{key}' が定義されていません。")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"設定キー '{key}' は空文字列です。")
        try:
            return float(stripped)
        except ValueError as exc:
            raise ValueError(f"設定キー '{key}' は数値である必要があります。") from exc
    raise ValueError(f"設定キー '{key}' は数値である必要があります。")


def _resolve_setting_str(mapping: Mapping[str, object], key: str) -> str:
    value = _require_str(mapping, key)
    return _resolve_env_placeholder(value, key)


def _resolve_setting_optional_str(mapping: Mapping[str, object], key: str) -> str | None:
    if key not in mapping:
        return None
    value = mapping[key]
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"設定キー '{key}' は文字列である必要があります。")
    return _resolve_env_placeholder(value, key)


def _resolve_env_placeholder(value: str, key: str) -> str:
    if not value.startswith("$"):
        return value
    env_key = value[1:]
    resolved = os.getenv(env_key)
    if resolved is None:
        raise ValueError(f"環境変数 '{env_key}' が未設定のため、設定キー '{key}' を解決できません。")
    return resolved


