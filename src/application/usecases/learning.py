"""
再学習フローのユースケーススケルトン。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Callable, Mapping, Protocol, Sequence

from application.services.feature_builder import FeatureBuilder, FeatureBuildRequest, FeatureBuildResult
from application.services.trainer import TrainerService, TrainingRequest
from domain import DatasetPartition, ModelArtifact, ThetaParams, ThetaRange
from domain.services import LabelingInput, LabelingOutput, LabelingService
from domain.value_objects import DataQualitySnapshot


@dataclass(frozen=True)
class LearningRequest:
    """
    再学習ユースケースの入力。
    """

    partitions: Sequence[DatasetPartition]
    feature_spec: Mapping[str, str]
    preprocessing: Mapping[str, str]
    theta_range: ThetaRange
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class LearningResponse:
    """
    再学習ユースケースの出力。
    """

    model_artifact: ModelArtifact
    backtest_metrics: Mapping[str, float]
    theta_params: ThetaParams
    diagnostics: Mapping[str, float] = field(default_factory=dict)


class AuditLogger(Protocol):
    """
    ユースケースの監査イベントを記録する。
    """

    def log(self, event_name: str, payload: Mapping[str, str]) -> None:
        ...


class LearningUseCase(Protocol):
    """
    再学習のユースケース。
    """

    def execute(self, request: LearningRequest) -> LearningResponse:
        ...


class LearningService(LearningUseCase):
    """特徴量生成・ラベリング・学習を統合するユースケース実装。"""

    def __init__(
        self,
        *,
        feature_builder: FeatureBuilder,
        labeling_service: LabelingService,
        trainer: TrainerService,
        default_ai1_params: Mapping[str, float] | None = None,
        default_ai2_params: Mapping[str, float] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._feature_builder = feature_builder
        self._labeling_service = labeling_service
        self._trainer = trainer
        self._default_ai1_params = dict(default_ai1_params or {"learning_rate": 0.1, "epochs": 200})
        self._default_ai2_params = dict(default_ai2_params or {"learning_rate": 0.1, "epochs": 200})
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def execute(self, request: LearningRequest) -> LearningResponse:
        if not request.partitions:
            raise ValueError("学習対象パーティションが指定されていません。")

        model_version = request.metadata.get("model_version") or self._generate_model_version()

        features: list[Mapping[str, float]] = []
        labels_ai1: list[int] = []
        labels_ai2: list[int] = []

        for partition in request.partitions:
            build_result = self._build_features(partition, request)
            labeling = self._labeling_service.generate(
                LabelingInput(partition=partition, features=build_result.features)
            )
            features.extend(build_result.features)
            labels_ai1.extend(labeling.ai1_labels)
            labels_ai2.extend(labeling.ai2_labels)

        if not features:
            raise ValueError("学習に利用可能な特徴量が存在しません。")

        aggregated_partition = self._aggregate_partition(request.partitions)

        training_request = TrainingRequest(
            partition=aggregated_partition,
            features=tuple(features),
            labels_ai1=tuple(labels_ai1),
            labels_ai2=tuple(labels_ai2),
            params_ai1=self._merge_params(self._default_ai1_params, request.metadata.get("params_ai1")),
            params_ai2=self._merge_params(self._default_ai2_params, request.metadata.get("params_ai2")),
            calibration=True,
            metadata=self._build_training_metadata(request, model_version),
        )

        training_result = self._trainer.run(training_request)

        diagnostics = self._extract_numeric_diagnostics(training_result.diagnostics)
        diagnostics["feature_count"] = float(len(features))

        theta_params = training_result.artifact.theta_params

        return LearningResponse(
            model_artifact=training_result.artifact.artifact,
            backtest_metrics=dict(training_result.cv_metrics),
            theta_params=theta_params,
            diagnostics=diagnostics,
        )

    def _build_features(
        self,
        partition: DatasetPartition,
        request: LearningRequest,
    ) -> FeatureBuildResult:
        snapshot = DataQualitySnapshot(
            bars_written=partition.bars_written,
            missing_gaps=partition.missing_gaps,
            outlier_bars=partition.outlier_bars,
            spike_flags=partition.spike_flags,
            quarantined=partition.quarantine_flag,
        )
        build_request = FeatureBuildRequest(
            partition=partition,
            feature_spec=request.feature_spec,
            preprocessing=request.preprocessing,
            dq_snapshot=snapshot,
            force_rebuild=request.metadata.get("force_rebuild", "false").lower() == "true",
        )
        return self._feature_builder.build(build_request)

    @staticmethod
    def _aggregate_partition(partitions: Sequence[DatasetPartition]) -> DatasetPartition:
        head = partitions[0]
        last_timestamp = max(p.last_timestamp for p in partitions)
        data_hash = sha256("".join(p.data_hash for p in partitions).encode("utf-8")).hexdigest()
        return DatasetPartition(
            timeframe=head.timeframe,
            symbol=head.symbol,
            year=last_timestamp.year,
            month=last_timestamp.month,
            last_timestamp=last_timestamp,
            bars_written=sum(p.bars_written for p in partitions),
            missing_gaps=sum(p.missing_gaps for p in partitions),
            outlier_bars=sum(p.outlier_bars for p in partitions),
            spike_flags=sum(p.spike_flags for p in partitions),
            quarantine_flag=any(p.quarantine_flag for p in partitions),
            data_hash=data_hash,
        )

    @staticmethod
    def _partition_ids(partitions: Sequence[DatasetPartition]) -> list[str]:
        return [f"{p.symbol}:{p.year:04d}-{p.month:02d}" for p in partitions]

    def _generate_model_version(self) -> str:
        return self._clock().strftime("model_%Y%m%d_%H%M%S")

    def _merge_params(
        self,
        defaults: Mapping[str, float],
        overrides: object,
    ) -> Mapping[str, float]:
        merged: dict[str, float] = dict(defaults)
        if isinstance(overrides, Mapping):
            for key, value in overrides.items():
                try:
                    merged[str(key)] = float(value)
                except (TypeError, ValueError):
                    continue
        return merged

    def _build_training_metadata(
        self,
        request: LearningRequest,
        model_version: str,
    ) -> Mapping[str, str]:
        metadata: dict[str, str] = {
            "model_version": model_version,
            "source_partitions": ",".join(self._partition_ids(request.partitions)),
        }
        for key, value in request.metadata.items():
            if key in {"params_ai1", "params_ai2"}:
                continue
            metadata[str(key)] = str(value)
        return metadata

    @staticmethod
    def _extract_numeric_diagnostics(source: Mapping[str, str]) -> dict[str, float]:
        diagnostics: dict[str, float] = {}
        for key, value in source.items():
            try:
                diagnostics[key] = float(value)
            except (TypeError, ValueError):
                continue
        return diagnostics

