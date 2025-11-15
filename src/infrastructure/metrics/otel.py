"""
OpenTelemetry のエクスポータ設定を行うユーティリティ。
"""

from __future__ import annotations

from typing import Mapping

from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

from .telemetry_runtime import TelemetryManager


class OpenTelemetryConfigurationError(ValueError):
    """OTel 設定値が不正な場合の例外。"""


def configure_tracing(options: Mapping[str, object], *, environment: str | None = None) -> None:
    enabled = bool(options.get("enabled", True))
    if not enabled:
        return

    endpoint = options.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint:
        raise OpenTelemetryConfigurationError("otel.endpoint が設定されていません。")

    timeout_raw = options.get("timeout_seconds", 10.0)
    timeout = int(_to_float(timeout_raw, "otel.timeout_seconds"))
    headers = options.get("headers")
    if headers is not None and not isinstance(headers, Mapping):
        raise OpenTelemetryConfigurationError("otel.headers は Mapping である必要があります。")

    service_name = options.get("service_name", "ml-assets-core")
    if not isinstance(service_name, str) or not service_name:
        raise OpenTelemetryConfigurationError("otel.service_name は非空の文字列である必要があります。")

    exporter = OTLPSpanExporter(
        endpoint=endpoint,
        insecure=bool(options.get("insecure", True)),
        timeout=timeout,
        headers={str(key): str(value) for key, value in headers.items()} if isinstance(headers, Mapping) else None,
    )

    TelemetryManager.configure(
        exporter=exporter,
        service_name=service_name,
        environment=environment,
    )


def _to_float(value: object, field: str) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError) as exc:
        raise OpenTelemetryConfigurationError(f"{field} は数値である必要があります。") from exc

