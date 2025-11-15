"""
Prometheus 実装に依存した MetricsRegistry。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence, cast

from prometheus_client import (
    CollectorRegistry,
    Counter as PrometheusCounter,
    Gauge as PrometheusGauge,
    Histogram as PrometheusHistogram,
    start_http_server,
)

from .prometheus_exporter import Counter, Gauge, Histogram, MetricsRegistry


class _GaugeAdapter(Gauge):
    def __init__(self, metric: PrometheusGauge) -> None:
        self._metric = metric

    def set(self, value: float, labels: Mapping[str, str] | None = None) -> None:
        if labels:
            self._metric.labels(**labels).set(value)
        else:
            self._metric.set(value)


class _CounterAdapter(Counter):
    def __init__(self, metric: PrometheusCounter) -> None:
        self._metric = metric

    def inc(self, value: float = 1.0, labels: Mapping[str, str] | None = None) -> None:
        if labels:
            self._metric.labels(**labels).inc(value)
        else:
            self._metric.inc(value)


class _HistogramAdapter(Histogram):
    def __init__(self, metric: PrometheusHistogram) -> None:
        self._metric = metric

    def observe(self, value: float, labels: Mapping[str, str] | None = None) -> None:
        if labels:
            self._metric.labels(**labels).observe(value)
        else:
            self._metric.observe(value)


def _normalize_label_names(labels: Sequence[str] | None) -> tuple[str, ...]:
    if not labels:
        return ()
    return tuple(sorted(labels))


@dataclass
class PrometheusMetricsRegistry(MetricsRegistry):
    """
    prometheus-client を利用する MetricsRegistry 実装。
    """

    registry: CollectorRegistry
    histogram_buckets: Mapping[str, Sequence[float]] | None = None

    _gauges: dict[tuple[str, tuple[str, ...]], PrometheusGauge] = field(default_factory=dict, init=False)
    _counters: dict[tuple[str, tuple[str, ...]], PrometheusCounter] = field(default_factory=dict, init=False)
    _histograms: dict[tuple[str, tuple[str, ...]], PrometheusHistogram] = field(default_factory=dict, init=False)

    def gauge(self, name: str, documentation: str, labels: tuple[str, ...] | None = None) -> Gauge:
        label_names = _normalize_label_names(labels)
        key = (name, label_names)
        metric = self._gauges.get(key)
        if metric is None:
            metric = PrometheusGauge(name, documentation, labelnames=label_names, registry=self.registry)
            self._gauges[key] = metric
        return _GaugeAdapter(metric)

    def counter(self, name: str, documentation: str, labels: tuple[str, ...] | None = None) -> Counter:
        label_names = _normalize_label_names(labels)
        key = (name, label_names)
        metric = self._counters.get(key)
        if metric is None:
            metric = PrometheusCounter(name, documentation, labelnames=label_names, registry=self.registry)
            self._counters[key] = metric
        return _CounterAdapter(metric)

    def histogram(self, name: str, documentation: str, labels: tuple[str, ...] | None = None) -> Histogram:
        label_names = _normalize_label_names(labels)
        key = (name, label_names)
        metric = self._histograms.get(key)
        if metric is None:
            bucket_values: tuple[float, ...] | None = None
            if self.histogram_buckets:
                raw = self.histogram_buckets.get(name)
                if raw:
                    bucket_values = tuple(float(boundary) for boundary in raw)
            if bucket_values is not None:
                metric = PrometheusHistogram(
                    name,
                    documentation,
                    labelnames=label_names,
                    buckets=cast("Sequence[float | str]", bucket_values),
                    registry=self.registry,
                )
            else:
                metric = PrometheusHistogram(
                    name,
                    documentation,
                    labelnames=label_names,
                    registry=self.registry,
                )
            self._histograms[key] = metric
        return _HistogramAdapter(metric)


def start_metrics_http_server(
    registry: CollectorRegistry,
    *,
    host: str,
    port: int,
) -> object | None:
    """
    Prometheus `/metrics` エンドポイントを公開する簡易HTTPサーバを起動する。
    port が 0 以下の場合はサーバを起動しない。
    """

    if port <= 0:
        return None
    thread = start_http_server(port, addr=host, registry=registry)
    return thread

