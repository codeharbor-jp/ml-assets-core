from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np

from application.services.trainer import ModelArtifactBuilder, ModelTrainerBackend, TimeSeriesCVStrategy, TrainingRequest
from domain import CalibrationMetrics, DatasetPartition, ModelArtifact, ThetaParams
from infrastructure.storage import LocalFileSystemStorageClient, ObjectStorageClient, StoragePathResolver


class RollingTimeSeriesCV(TimeSeriesCVStrategy):
    """単純な時間順の逐次 CV。"""

    def __init__(self, *, folds: int = 3, min_train_size: int = 20, holdout_size: int = 10) -> None:
        if folds <= 0:
            raise ValueError("folds は 1 以上で指定してください。")
        self._folds = folds
        self._min_train_size = max(min_train_size, 1)
        self._holdout_size = max(holdout_size, 1)

    def split(
        self,
        *,
        partition: DatasetPartition,
        features: Sequence[Mapping[str, float]],
        labels: Sequence[int],
    ) -> Iterable[tuple[Sequence[int], Sequence[int]]]:  # noqa: D401
        size = len(features)
        if size <= self._min_train_size + self._holdout_size:
            train_end = max(size - 1, 1)
            train_idx = tuple(range(train_end))
            valid_idx = tuple(range(train_end, size)) or tuple(range(train_end))
            yield train_idx, valid_idx
            return

        step = max((size - self._min_train_size) // self._folds, 1)
        for split_end in range(self._min_train_size + self._holdout_size, size + 1, step):
            train_end = max(split_end - self._holdout_size, 1)
            train_idx = tuple(range(train_end))
            valid_idx = tuple(range(train_end, min(split_end, size)))
            if not valid_idx:
                continue
            yield train_idx, valid_idx


class LogisticModelTrainer(ModelTrainerBackend):
    """単純なロジスティック回帰バックエンド実装。"""

    def __init__(
        self,
        *,
        learning_rate: float = 0.1,
        epochs: int = 200,
        l2: float = 1e-4,
        clip_min: float = 1e-6,
        clip_max: float = 1 - 1e-6,
    ) -> None:
        self._learning_rate = learning_rate
        self._epochs = epochs
        self._l2 = l2
        self._clip_min = clip_min
        self._clip_max = clip_max
        self._weights: np.ndarray | None = None
        self._feature_keys: list[str] = []

    def fit(
        self,
        *,
        train_features: Sequence[Mapping[str, float]],
        train_labels: Sequence[int],
        valid_features: Sequence[Mapping[str, float]],
        valid_labels: Sequence[int],
        params: Mapping[str, float],
    ) -> Mapping[str, float]:
        if not train_features:
            raise ValueError("学習特徴量が空です。")
        self._feature_keys = sorted({key for row in train_features for key in row})
        lr = float(params.get("learning_rate", self._learning_rate))
        epochs = int(params.get("epochs", self._epochs))
        l2 = float(params.get("l2", self._l2))

        X = self._to_matrix(train_features)
        y = np.array(train_labels, dtype=float)
        if self._weights is None or self._weights.shape[0] != X.shape[1]:
            self._weights = np.zeros(X.shape[1])

        for _ in range(max(epochs, 1)):
            logits = X @ self._weights
            pred = self._sigmoid(logits)
            gradient = X.T @ (pred - y) / X.shape[0] + l2 * self._weights
            self._weights -= lr * gradient

        metrics = self._evaluate(valid_features, valid_labels)
        return metrics

    def calibrate(
        self,
        *,
        valid_features: Sequence[Mapping[str, float]],
        valid_labels: Sequence[int],
    ) -> CalibrationMetrics:
        if not valid_features:
            return CalibrationMetrics(
                brier_score=0.0,
                expected_calibration_error=0.0,
                maximum_calibration_error=0.0,
                log_loss=0.0,
                sample_size=1,
            )
        preds = self._predict_proba(valid_features)
        clipped = np.clip(preds, self._clip_min, self._clip_max)
        labels = np.array(valid_labels, dtype=float)
        brier = float(np.mean((clipped - labels) ** 2))
        log_loss = float(-np.mean(labels * np.log(clipped) + (1 - labels) * np.log(1 - clipped)))
        abs_errors = np.abs(clipped - labels)
        ece = float(np.mean(abs_errors))
        max_ce = float(np.max(abs_errors))
        return CalibrationMetrics(
            brier_score=brier,
            expected_calibration_error=ece,
            maximum_calibration_error=max_ce,
            log_loss=log_loss,
            sample_size=len(valid_labels),
        )

    def dump_state(self) -> Mapping[str, object]:
        return {
            "feature_keys": list(self._feature_keys),
            "weights": self._weights.tolist() if self._weights is not None else [],
        }

    def _evaluate(self, features: Sequence[Mapping[str, float]], labels: Sequence[int]) -> Mapping[str, float]:
        if not features:
            return {"loss": 0.0, "accuracy": 0.0}
        preds = self._predict_proba(features)
        labels_arr = np.array(labels, dtype=int)
        clipped = np.clip(preds, self._clip_min, self._clip_max)
        log_loss = float(-np.mean(labels_arr * np.log(clipped) + (1 - labels_arr) * np.log(1 - clipped)))
        pred_classes = (preds >= 0.5).astype(int)
        accuracy = float(np.mean(pred_classes == labels_arr))
        precision = float(np.sum((pred_classes == 1) & (labels_arr == 1)) / max(np.sum(pred_classes == 1), 1))
        recall = float(np.sum((pred_classes == 1) & (labels_arr == 1)) / max(np.sum(labels_arr == 1), 1))
        return {
            "loss": log_loss,
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
        }

    def _predict_proba(self, features: Sequence[Mapping[str, float]]) -> np.ndarray:
        X = self._to_matrix(features)
        logits = X @ self._weights
        return self._sigmoid(logits)

    def _to_matrix(self, features: Sequence[Mapping[str, float]]) -> np.ndarray:
        if not self._feature_keys:
            self._feature_keys = sorted({key for row in features for key in row})
        matrix = np.zeros((len(features), len(self._feature_keys) + 1))
        matrix[:, 0] = 1.0
        for row_idx, row in enumerate(features):
            for col_idx, key in enumerate(self._feature_keys, start=1):
                matrix[row_idx, col_idx] = float(row.get(key, 0.0))
        return matrix

    @staticmethod
    def _sigmoid(values: np.ndarray) -> np.ndarray:
        positive = values >= 0
        z = np.zeros_like(values, dtype=float)
        z[positive] = np.exp(-values[positive])
        z[~positive] = np.exp(values[~positive])
        sigmoid = np.zeros_like(values, dtype=float)
        sigmoid[positive] = 1.0 / (1.0 + z[positive])
        sigmoid[~positive] = z[~positive] / (1.0 + z[~positive])
        return sigmoid


class SimpleThetaEstimator:
    """CV メトリクスから単純に θ を推定する実装。"""

    def estimate(
        self,
        *,
        request: "TrainingRequest",
        cv_metrics: Mapping[str, float],
        calibration_metrics: CalibrationMetrics,
    ) -> ThetaParams:
        accuracy = cv_metrics.get("ai1_cv_accuracy", 0.7)
        theta1 = float(min(max(accuracy, 0.5), 0.95))
        theta2 = float(min(max(1.0 - accuracy, 0.1), 0.9))
        return ThetaParams(
            theta1=theta1,
            theta2=theta2,
            updated_at=datetime.now(timezone.utc),
            updated_by=request.metadata.get("requested_by", "learning-service"),
            source_model_version=request.metadata.get("model_version"),
        )


@dataclass
class LocalModelArtifactBuilder(ModelArtifactBuilder):
    path_resolver: StoragePathResolver
    storage_client: ObjectStorageClient = field(default_factory=LocalFileSystemStorageClient)

    def build(
        self,
        *,
        request: "TrainingRequest",
        metrics: Mapping[str, float],
        model_state: Mapping[str, Mapping[str, object]] | None = None,
    ) -> ModelArtifact:
        model_version = request.metadata.get("model_version") or self._generate_model_version()
        models_root = self.path_resolver.resolve("models_root")
        model_dir = Path(models_root) / model_version
        self.storage_client.makedirs(model_dir)

        created_at = datetime.now(timezone.utc)
        created_by = request.metadata.get("requested_by", "learning-service")

        ai1_path = model_dir / "ai1_model.json"
        ai2_path = model_dir / "ai2_model.json"
        metrics_path = model_dir / "metrics.json"
        params_path = model_dir / "params.json"
        schema_path = model_dir / "feature_schema.json"

        state_payload = model_state or {}
        self._write_json(ai1_path, state_payload.get("ai1", {}))
        self._write_json(ai2_path, state_payload.get("ai2", {}))
        self._write_json(metrics_path, metrics)
        self._write_json(
            params_path,
            {
                "params_ai1": dict(request.params_ai1),
                "params_ai2": dict(request.params_ai2),
                "metadata": dict(request.metadata),
            },
        )

        feature_keys = sorted({key for row in request.features for key in row})
        self._write_json(
            schema_path,
            {
                "feature_keys": feature_keys,
                "timestamp": created_at.isoformat(),
            },
        )

        code_hash = request.metadata.get("code_hash", "unknown")
        data_hash = request.partition.data_hash

        return ModelArtifact(
            model_version=model_version,
            created_at=created_at,
            created_by=created_by,
            ai1_path=ai1_path,
            ai2_path=ai2_path,
            feature_schema_path=schema_path,
            params_path=params_path,
            metrics_path=metrics_path,
            code_hash=code_hash,
            data_hash=data_hash,
        )

    def _write_json(self, path: Path, payload: Mapping[str, object] | Sequence[object]) -> None:
        client = self.storage_client
        client.makedirs(path.parent)
        with client.open_write(path) as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))

    @staticmethod
    def _generate_model_version() -> str:
        timestamp = datetime.now(timezone.utc)
        return timestamp.strftime("%Y%m%d_%H%M%S")
