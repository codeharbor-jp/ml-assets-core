"""
アプリケーション層から利用する観測性ユーティリティ。

Infrastructure 層で実際のメトリクス・トレーシング実装を登録するまでは
全て no-op として動作する。
"""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from typing import Callable, ContextManager, Mapping, Protocol


class MetricsRecorderProtocol(Protocol):
    def observe_inference_latency(self, worker_id: str, latency_ms: float) -> None: ...

    def increment_signals_published(self, worker_id: str, count: int) -> None: ...

    def observe_feature_build(self, symbol: str, duration_seconds: float, cached: bool) -> None: ...

    def observe_training_duration(self, model_version: str, duration_seconds: float) -> None: ...

    def increment_retrain_success(self, status: str) -> None: ...

    def observe_backtest_duration(self, model_version: str, duration_seconds: float) -> None: ...

    def increment_theta_trials(self, phase: str, trials: int) -> None: ...

    def reset(self) -> None: ...


class _NoopMetricsRecorder(MetricsRecorderProtocol):
    def observe_inference_latency(self, worker_id: str, latency_ms: float) -> None:  # noqa: D401
        pass

    def increment_signals_published(self, worker_id: str, count: int) -> None:
        pass

    def observe_feature_build(self, symbol: str, duration_seconds: float, cached: bool) -> None:
        pass

    def observe_training_duration(self, model_version: str, duration_seconds: float) -> None:
        pass

    def increment_retrain_success(self, status: str) -> None:
        pass

    def observe_backtest_duration(self, model_version: str, duration_seconds: float) -> None:
        pass

    def increment_theta_trials(self, phase: str, trials: int) -> None:
        pass

    def reset(self) -> None:
        pass


metrics_recorder: MetricsRecorderProtocol = _NoopMetricsRecorder()
_telemetry_span_factory: (
    Callable[[str, Mapping[str, object] | None], ContextManager[object]] | None
) = None


def use_metrics_recorder(recorder: MetricsRecorderProtocol) -> None:
    global metrics_recorder
    metrics_recorder = recorder


def use_telemetry_span(
    factory: Callable[[str, Mapping[str, object] | None], ContextManager[object]] | None,
) -> None:
    """
    factory は (name: str, attributes: Mapping[str, object] | None) -> context manager を返す callable。
    """

    global _telemetry_span_factory
    _telemetry_span_factory = factory


@contextmanager
def telemetry_span(name: str, attributes: Mapping[str, object] | None = None):
    if _telemetry_span_factory is None:
        with nullcontext():
            yield None
            return
    with _telemetry_span_factory(name, attributes):
        yield None


def reset_observability() -> None:
    use_metrics_recorder(_NoopMetricsRecorder())
    use_telemetry_span(None)

