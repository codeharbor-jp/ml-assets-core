"""
OpenTelemetry ランタイムの初期化とスパン生成ヘルパ。
"""

from __future__ import annotations

import atexit
from contextlib import contextmanager
from typing import Mapping

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter


class TelemetryManager:
    _tracer_provider: TracerProvider | None = None
    _tracer = trace.get_tracer(__name__)
    _configured = False

    @classmethod
    def configure(
        cls,
        *,
        exporter: SpanExporter,
        service_name: str,
        environment: str | None = None,
        additional_resources: Mapping[str, str] | None = None,
    ) -> None:
        resource_attributes = {"service.name": service_name}
        if environment:
            resource_attributes["deployment.environment"] = environment
        if additional_resources:
            resource_attributes.update(additional_resources)

        resource = Resource.create(resource_attributes)
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(tracer_provider)
        cls._tracer_provider = tracer_provider
        cls._tracer = trace.get_tracer(service_name)
        cls._configured = True

        atexit.register(cls._shutdown)

    @classmethod
    def _shutdown(cls) -> None:
        if cls._tracer_provider is not None:
            cls._tracer_provider.shutdown()
            cls._tracer_provider = None
        cls._configured = False

    @classmethod
    @contextmanager
    def span(cls, name: str, attributes: Mapping[str, object] | None = None):
        if not cls._configured:
            yield None
            return
        with cls._tracer.start_as_current_span(name) as span:
            if attributes:
                for key, value in attributes.items():
                    if isinstance(value, (str, bool, int, float)):
                        span.set_attribute(key, value)
                    elif isinstance(value, (list, tuple)):
                        if all(isinstance(item, (str, bool, int, float)) for item in value):
                            span.set_attribute(key, list(value))
                        else:
                            span.set_attribute(key, [str(item) for item in value])
                    else:
                        span.set_attribute(key, str(value))
            yield span


def telemetry_span(name: str, attributes: Mapping[str, object] | None = None):
    """
    `with telemetry_span("operation"):` 形式で利用するヘルパ。
    """

    return TelemetryManager.span(name, attributes=attributes)

