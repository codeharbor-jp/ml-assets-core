"""
特徴量生成・キャッシュ管理を担うサービス定義。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Protocol, Sequence

from ...domain import DatasetPartition, DataQualityFlag, DataQualitySnapshot

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

