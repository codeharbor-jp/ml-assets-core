"""
Prometheus エクスポータのスケルトン。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol


class Gauge(Protocol):
    def set(self, value: float, labels: Mapping[str, str] | None = None) -> None:
        ...


class Counter(Protocol):
    def inc(self, value: float = 1.0, labels: Mapping[str, str] | None = None) -> None:
        ...


class Histogram(Protocol):
    def observe(self, value: float, labels: Mapping[str, str] | None = None) -> None:
        ...


class MetricsRegistry(Protocol):
    """
    Prometheus レジストリを抽象化。
    """

    def gauge(self, name: str, documentation: str, labels: tuple[str, ...] | None = None) -> Gauge:
        ...

    def counter(self, name: str, documentation: str, labels: tuple[str, ...] | None = None) -> Counter:
        ...

    def histogram(self, name: str, documentation: str, labels: tuple[str, ...] | None = None) -> Histogram:
        ...


@dataclass
class PrometheusExporter:
    """
    アプリケーションメトリクスを登録・操作するエクスポータ。
    """

    registry: MetricsRegistry

    def emit_latency(self, name: str, value_ms: float, *, labels: Mapping[str, str] | None = None) -> None:
        histogram = self.registry.histogram(
            name,
            f"{name} latency milliseconds",
            labels=tuple(labels.keys()) if labels else None,
        )
        histogram.observe(value_ms, labels=labels)

    def emit_counter(self, name: str, value: float = 1.0, *, labels: Mapping[str, str] | None = None) -> None:
        counter = self.registry.counter(
            name,
            f"{name} counter",
            labels=tuple(labels.keys()) if labels else None,
        )
        counter.inc(value, labels=labels)

    def emit_gauge(self, name: str, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        gauge = self.registry.gauge(
            name,
            f"{name} gauge",
            labels=tuple(labels.keys()) if labels else None,
        )
        gauge.set(value, labels=labels)

