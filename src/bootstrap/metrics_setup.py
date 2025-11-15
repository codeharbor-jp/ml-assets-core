"""
メトリクス初期化ロジック。
"""

from __future__ import annotations

from typing import Any, Mapping

from prometheus_client import CollectorRegistry

from application.observability import reset_observability, use_metrics_recorder, use_telemetry_span
from infrastructure.metrics import (
    MetricsRecorder,
    PrometheusMetricsRegistry,
    configure_tracing,
    start_metrics_http_server,
)
from infrastructure.metrics.telemetry_runtime import TelemetryManager

from .container import InvalidConfigurationError, MetricsConfigurator

class MetricsConfiguratorRegistry(MetricsConfigurator):
    """
    provider 名に応じて委譲するディスパッチャ。
    """

    def __init__(self, delegates: Mapping[str, MetricsConfigurator]) -> None:
        if not delegates:
            raise ValueError("メトリクス設定の委譲先が定義されていません。")
        self._delegates = dict(delegates)

    def configure(self, config: Mapping[str, Any]) -> None:
        provider = _require_string(config, "provider")
        delegate = self._delegates.get(provider)
        if delegate is None:
            raise InvalidConfigurationError(
                f"metrics provider '{provider}' に対応する初期化ロジックが見つかりません。"
            )
        delegate.configure(config)


class NoopMetricsConfigurator(MetricsConfigurator):
    """
    provider == noop の場合に適用するダミー実装。
    """

    EXPECTED_PROVIDER = "noop"

    def configure(self, config: Mapping[str, Any]) -> None:
        provider = _require_string(config, "provider")
        if provider != self.EXPECTED_PROVIDER:
            raise InvalidConfigurationError(
                f"provider '{provider}' は NoopMetricsConfigurator では扱えません。"
            )
        # noop: テストやローカル開発でメトリクス初期化をスキップする場合に使用する。
        reset_observability()


class PrometheusMetricsConfigurator(MetricsConfigurator):
    EXPECTED_PROVIDER = "prometheus"

    def configure(self, config: Mapping[str, Any]) -> None:
        provider = _require_string(config, "provider")
        if provider != self.EXPECTED_PROVIDER:
            raise InvalidConfigurationError(
                f"provider '{provider}' は PrometheusMetricsConfigurator では扱えません。"
            )

        options = config.get("options", {})
        if not isinstance(options, Mapping):
            raise InvalidConfigurationError("metrics.options は Mapping である必要があります。")

        registry = CollectorRegistry()
        histogram_buckets = _parse_histogram_buckets(options.get("histogram_buckets"))

        prometheus_registry = PrometheusMetricsRegistry(
            registry=registry,
            histogram_buckets=histogram_buckets,
        )

        default_labels = _parse_default_labels(options.get("default_labels"))
        MetricsRecorder.configure(prometheus_registry, default_labels=default_labels)
        use_metrics_recorder(MetricsRecorder)
        use_telemetry_span(TelemetryManager.span)

        host = str(options.get("host", "0.0.0.0"))
        port = int(float(options.get("port", 0)))
        start_metrics_http_server(registry, host=host, port=port)

        otel_options = options.get("otel")
        if isinstance(otel_options, Mapping):
            configure_tracing(otel_options, environment=default_labels.get("environment"))


def _require_string(config: Mapping[str, Any], key: str) -> str:
    if key not in config:
        raise InvalidConfigurationError(f"metrics 設定に '{key}' が存在しません。")
    value = config[key]
    if not isinstance(value, str) or not value:
        raise InvalidConfigurationError(f"metrics 設定の '{key}' は非空の str である必要があります。")
    return value


def _parse_histogram_buckets(raw: object) -> Mapping[str, tuple[float, ...]]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise InvalidConfigurationError("metrics.options.histogram_buckets は Mapping である必要があります。")
    buckets: dict[str, tuple[float, ...]] = {}
    for metric, values in raw.items():
        if not isinstance(metric, str) or not metric:
            raise InvalidConfigurationError("histogram_buckets のキーは非空の文字列である必要があります。")
        if not isinstance(values, (list, tuple)):
            raise InvalidConfigurationError(f"histogram_buckets['{metric}'] は配列である必要があります。")
        try:
            buckets[metric] = tuple(float(value) for value in values)
        except (TypeError, ValueError) as exc:
            raise InvalidConfigurationError(
                f"histogram_buckets['{metric}'] の値は数値である必要があります。"
            ) from exc
    return buckets


def _parse_default_labels(raw: object) -> Mapping[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise InvalidConfigurationError("metrics.options.default_labels は Mapping である必要があります。")
    labels: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key:
            raise InvalidConfigurationError("default_labels のキーは非空の文字列である必要があります。")
        labels[key] = str(value)
    return labels

