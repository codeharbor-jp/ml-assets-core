"""
OpenTelemetry トレーシングのスケルトン。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class TracerProvider(Protocol):
    def force_flush(self, timeout_millis: int | None = None) -> bool:
        ...


class MeterProvider(Protocol):
    def shutdown(self) -> None:
        ...


@dataclass
class TelemetryConfigurator:
    """
    OpenTelemetry の初期化・クリーンアップを担う。
    """

    tracer_provider: TracerProvider
    meter_provider: MeterProvider

    def flush(self) -> None:
        self.tracer_provider.force_flush()

    def shutdown(self) -> None:
        self.meter_provider.shutdown()

