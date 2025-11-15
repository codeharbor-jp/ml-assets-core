"""
特徴量生成・キャッシュ管理を担うサービス定義。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Protocol, Sequence

from application.observability import metrics_recorder, telemetry_span

from domain import DataQualityFlag, DataQualitySnapshot, DatasetPartition

FeatureVector = Mapping[str, float]


class FeatureCache(Protocol):
    """
    特徴量キャッシュへのアクセスインターフェース。
    """

    def exists(self, *, partition: DatasetPartition, feature_hash: str) -> bool:
        ...

    def load(self, *, partition: DatasetPartition, feature_hash: str) -> Iterable[FeatureVector]:
        ...

    def store(
        self,
        *,
        partition: DatasetPartition,
        feature_hash: str,
        features: Iterable[FeatureVector],
        schema_hash: str,
    ) -> None:
        ...

    def invalidate(self, *, partition: DatasetPartition, reason: str) -> None:
        ...


class FeatureHasher(Protocol):
    """
    特徴量定義と前処理設定からハッシュを算出するインターフェース。
    """

    def compute_hash(self, feature_spec: Mapping[str, str], preprocessing: Mapping[str, str]) -> str:
        ...


class FeatureGenerator(Protocol):
    """
    生データと設定から特徴量を生成するインターフェース。
    """

    def generate(
        self,
        *,
        partition: DatasetPartition,
        feature_spec: Mapping[str, str],
        preprocessing: Mapping[str, str],
    ) -> Iterable[FeatureVector]:
        ...


@dataclass(frozen=True)
class FeatureBuildRequest:
    """
    特徴量生成フローの入力。
    """

    partition: DatasetPartition
    feature_spec: Mapping[str, str]
    preprocessing: Mapping[str, str]
    dq_snapshot: DataQualitySnapshot
    force_rebuild: bool = False


@dataclass(frozen=True)
class FeatureBuildResult:
    """
    特徴量生成の結果。
    """

    partition: DatasetPartition
    feature_hash: str
    schema_hash: str
    features: Sequence[FeatureVector]
    dq_flag: DataQualityFlag
    metadata: Mapping[str, str] = field(default_factory=dict)


class FeatureBuilderService(Protocol):
    """
    特徴量生成・キャッシュ操作を統括するサービス。
    """

    def build(self, request: FeatureBuildRequest) -> FeatureBuildResult:
        ...


class FeatureBuildError(RuntimeError):
    """特徴量生成に失敗した場合の基底例外。"""


class QuarantinedPartitionError(FeatureBuildError):
    """隔離対象パーティションのため特徴量生成が許可されない。"""


class DataQualityThresholdExceededError(FeatureBuildError):
    """データ品質閾値を超過した場合の例外。"""

    def __init__(self, flag: DataQualityFlag, message: str) -> None:
        super().__init__(message)
        self.flag = flag


@dataclass(frozen=True)
class FeatureBuilderConfig:
    """
    データ品質に関する閾値と挙動を制御する設定。
    """

    missing_threshold: float = 0.05
    outlier_threshold: float = 0.02
    spike_threshold: float = 0.01
    allow_warning: bool = True
    invalidate_on_failure: bool = True


class FeatureBuilder:
    """
    FeatureCache と FeatureGenerator を組み合わせて特徴量生成を行う実装。
    """

    def __init__(
        self,
        cache: FeatureCache,
        generator: FeatureGenerator,
        hasher: FeatureHasher,
        config: FeatureBuilderConfig | None = None,
    ) -> None:
        self._cache = cache
        self._generator = generator
        self._hasher = hasher
        self._config = config or FeatureBuilderConfig()

    def build(self, request: FeatureBuildRequest) -> FeatureBuildResult:
        with telemetry_span(
            "feature_builder.build",
            {
                "partition.symbol": request.partition.symbol,
                "partition.timeframe": request.partition.timeframe,
            },
        ):
            start = time.perf_counter()

            dq_flag = self._evaluate_quality(request)
            if dq_flag == DataQualityFlag.QUARANTINE:
                self._invalidate_cache(request, reason="partition_quarantined")
                raise QuarantinedPartitionError(
                    f"Partition {request.partition.symbol} is quarantined and cannot be processed."
                )

            if not self._is_allowed_flag(dq_flag):
                self._invalidate_cache(request, reason=f"dq_flag_{dq_flag.value}")
                raise DataQualityThresholdExceededError(
                    dq_flag,
                    f"Partition {request.partition.symbol} exceeded data quality threshold ({dq_flag.value}).",
                )

            feature_hash = self._hasher.compute_hash(request.feature_spec, request.preprocessing)
            schema_hash = self._hasher.compute_hash(request.feature_spec, {})

            cached = False
            if request.force_rebuild:
                self._invalidate_cache(request, reason="force_rebuild")

            if not request.force_rebuild and self._cache.exists(partition=request.partition, feature_hash=feature_hash):
                cached = True
                feature_iterable = self._cache.load(partition=request.partition, feature_hash=feature_hash)
            else:
                feature_iterable = self._generator.generate(
                    partition=request.partition,
                    feature_spec=request.feature_spec,
                    preprocessing=request.preprocessing,
                )

            features: tuple[FeatureVector, ...] = tuple(feature_iterable)

            if not cached:
                self._cache.store(
                    partition=request.partition,
                    feature_hash=feature_hash,
                    features=features,
                    schema_hash=schema_hash,
                )

            metadata = {
                "feature_hash": feature_hash,
                "schema_hash": schema_hash,
                "cached": "true" if cached else "false",
            }

            duration = time.perf_counter() - start
            metrics_recorder.observe_feature_build(
                request.partition.symbol,
                duration_seconds=duration,
                cached=cached,
            )

            return FeatureBuildResult(
                partition=request.partition,
                feature_hash=feature_hash,
                schema_hash=schema_hash,
                features=features,
                dq_flag=dq_flag,
                metadata=metadata,
            )

    def _evaluate_quality(self, request: FeatureBuildRequest) -> DataQualityFlag:
        snapshot = request.dq_snapshot
        cfg = self._config
        return snapshot.evaluate(
            missing_threshold=cfg.missing_threshold,
            outlier_threshold=cfg.outlier_threshold,
            spike_threshold=cfg.spike_threshold,
        )

    def _is_allowed_flag(self, flag: DataQualityFlag) -> bool:
        allowed = {DataQualityFlag.OK}
        if self._config.allow_warning:
            allowed.add(DataQualityFlag.WARNING)
        return flag in allowed

    def _invalidate_cache(self, request: FeatureBuildRequest, *, reason: str) -> None:
        if not self._config.invalidate_on_failure:
            return
        try:
            self._cache.invalidate(partition=request.partition, reason=reason)
        except Exception:
            # キャッシュ無効化で発生した例外はこれ以上伝播させない。
            pass

