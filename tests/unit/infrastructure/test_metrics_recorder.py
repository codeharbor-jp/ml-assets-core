from __future__ import annotations

from prometheus_client import CollectorRegistry

from infrastructure.metrics.prometheus_runtime import PrometheusMetricsRegistry
from infrastructure.metrics.recorder import MetricsRecorder


def test_metrics_recorder_updates_prometheus_metrics() -> None:
    registry = CollectorRegistry()
    metrics_registry = PrometheusMetricsRegistry(registry=registry)
    MetricsRecorder.configure(metrics_registry, default_labels={"service": "test"})

    MetricsRecorder.observe_inference_latency("worker-1", 50.0)
    MetricsRecorder.increment_signals_published("worker-1", 2)
    MetricsRecorder.observe_feature_build("EURUSD", duration_seconds=0.5, cached=False)
    MetricsRecorder.increment_theta_trials("optuna", 3)

    latency_sum = registry.get_sample_value(
        "inference_latency_ms_sum",
        labels={"worker_id": "worker-1", "service": "test"},
    )
    assert latency_sum == 50.0

    signals_total = registry.get_sample_value(
        "signals_published_total",
        labels={"worker_id": "worker-1", "service": "test"},
    )
    assert signals_total == 2.0

    feature_count = registry.get_sample_value(
        "feature_build_invocations_total",
        labels={"symbol": "EURUSD", "cached": "false", "service": "test"},
    )
    assert feature_count == 1.0

    theta_total = registry.get_sample_value(
        "core_theta_trials_total",
        labels={"phase": "optuna", "service": "test"},
    )
    assert theta_total == 3.0

    MetricsRecorder.reset()

