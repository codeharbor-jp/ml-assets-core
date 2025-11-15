"""
アプリケーション共通で利用するメトリクス記録ユーティリティ。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .prometheus_exporter import Counter, Histogram, MetricsRegistry


@dataclass
class _MetricHandles:
    inference_latency_ms: Histogram
    signals_published_total: Counter
    feature_build_duration_seconds: Histogram
    feature_build_total: Counter
    core_retrain_duration_seconds: Histogram
    core_backtest_duration_seconds: Histogram
    theta_trials_total: Counter
    retrain_success_total: Counter


class MetricsRecorder:
    """
    グローバルなメトリクス記録を担当するヘルパ。
    MetricsRegistry が未設定の場合はすべての更新を無視する。
    """

    _registry: MetricsRegistry | None = None
    _handles: _MetricHandles | None = None
    _default_labels: Mapping[str, str] = {}

    @classmethod
    def configure(
        cls,
        registry: MetricsRegistry,
        *,
        default_labels: Mapping[str, str] | None = None,
    ) -> None:
        cls._registry = registry
        cls._default_labels = default_labels or {}
        base_label_names = tuple(cls._default_labels.keys())

        def _label_names(*names: str) -> tuple[str, ...]:
            return base_label_names + names

        cls._handles = _MetricHandles(
            inference_latency_ms=registry.histogram(
                "inference_latency_ms",
                "Inference latency per worker in milliseconds",
                labels=_label_names("worker_id"),
            ),
            signals_published_total=registry.counter(
                "signals_published",
                "Number of signals published to downstream queues",
                labels=_label_names("worker_id"),
            ),
            feature_build_duration_seconds=registry.histogram(
                "feature_build_duration_seconds",
                "Duration to build features per partition",
                labels=_label_names("symbol", "cached"),
            ),
            feature_build_total=registry.counter(
                "feature_build_invocations",
                "Number of feature build executions",
                labels=_label_names("symbol", "cached"),
            ),
            core_retrain_duration_seconds=registry.histogram(
                "core_retrain_duration_seconds",
                "Duration of trainer.run invocations in seconds",
                labels=_label_names("model_version"),
            ),
            core_backtest_duration_seconds=registry.histogram(
                "core_backtest_duration_seconds",
                "Duration of backtester.run invocations in seconds",
                labels=_label_names("model_version"),
            ),
            theta_trials_total=registry.counter(
                "core_theta_trials",
                "Number of theta optimisation trials",
                labels=_label_names("phase"),
            ),
            retrain_success_total=registry.counter(
                "core_retrain_success",
                "Number of successful retrain executions",
                labels=_label_names("status"),
            ),
        )

    @classmethod
    def _merge_labels(cls, extra: Mapping[str, str] | None) -> Mapping[str, str]:
        if not extra:
            return cls._default_labels
        merged = dict(cls._default_labels)
        merged.update(extra)
        return merged

    @classmethod
    def observe_inference_latency(cls, worker_id: str, latency_ms: float) -> None:
        if not cls._handles:
            return
        labels = cls._merge_labels({"worker_id": worker_id})
        cls._handles.inference_latency_ms.observe(latency_ms, labels=labels)

    @classmethod
    def increment_signals_published(cls, worker_id: str, count: int) -> None:
        if not cls._handles or count <= 0:
            return
        labels = cls._merge_labels({"worker_id": worker_id})
        cls._handles.signals_published_total.inc(count, labels=labels)

    @classmethod
    def observe_feature_build(cls, symbol: str, duration_seconds: float, cached: bool) -> None:
        if not cls._handles:
            return
        cache_label = "true" if cached else "false"
        labels = cls._merge_labels({"symbol": symbol, "cached": cache_label})
        cls._handles.feature_build_duration_seconds.observe(duration_seconds, labels=labels)
        cls._handles.feature_build_total.inc(1.0, labels=labels)

    @classmethod
    def observe_training_duration(cls, model_version: str, duration_seconds: float) -> None:
        if not cls._handles:
            return
        labels = cls._merge_labels({"model_version": model_version})
        cls._handles.core_retrain_duration_seconds.observe(duration_seconds, labels=labels)

    @classmethod
    def increment_retrain_success(cls, status: str) -> None:
        if not cls._handles:
            return
        labels = cls._merge_labels({"status": status})
        cls._handles.retrain_success_total.inc(1.0, labels=labels)

    @classmethod
    def observe_backtest_duration(cls, model_version: str, duration_seconds: float) -> None:
        if not cls._handles:
            return
        labels = cls._merge_labels({"model_version": model_version})
        cls._handles.core_backtest_duration_seconds.observe(duration_seconds, labels=labels)

    @classmethod
    def increment_theta_trials(cls, phase: str, trials: int) -> None:
        if not cls._handles or trials <= 0:
            return
        labels = cls._merge_labels({"phase": phase})
        cls._handles.theta_trials_total.inc(float(trials), labels=labels)

    @classmethod
    def reset(cls) -> None:
        cls._registry = None
        cls._handles = None
        cls._default_labels = {}

