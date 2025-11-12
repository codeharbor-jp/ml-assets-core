"""
市場データ取得アダプタの抽象定義。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Protocol, Sequence


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
    candles: Sequence[Mapping[str, float]]
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
    ) -> Sequence[Mapping[str, float]]:
        ...


class TwelveDataAdapter(MarketDataProvider):
    """
    TwelveData クライアントを利用して MarketDataProvider を実装するアダプタ。
    """

    def __init__(self, client: TwelveDataClient, provider_name: str = "twelvedata") -> None:
        self._client = client
        self._provider_name = provider_name

    def fetch(self, request: MarketDataRequest) -> MarketDataResponse:
        candles: list[Mapping[str, float]] = []
        for symbol in request.symbols:
            data = self._client.fetch_candles(
                symbol=symbol,
                interval=request.timeframe,
                start_at=request.start_at,
                end_at=request.end_at,
            )
            candles.extend(data)

        metadata = ProviderMetadata(provider_name=self._provider_name, latency_ms=0.0)
        return MarketDataResponse(
            status=ProviderStatus.OK,
            candles=candles,
            metadata=metadata,
        )

