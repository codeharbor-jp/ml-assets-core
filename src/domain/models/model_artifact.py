"""
モデルアーティファクトのドメインエンティティ。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class ModelArtifact:
    """
    再学習で生成されるモデル成果物のメタデータ。
    """

    model_version: str
    created_at: datetime
    created_by: str
    ai1_path: Path
    ai2_path: Path
    feature_schema_path: Path
    params_path: Path
    metrics_path: Path
    code_hash: str
    data_hash: str
    notes: str | None = None

    def __post_init__(self) -> None:
        if not self.model_version:
            raise ValueError("model_version は必須です。")
        if not self.created_by:
            raise ValueError("created_by は必須です。")
        for attribute in ("ai1_path", "ai2_path", "feature_schema_path", "params_path", "metrics_path"):
            path = getattr(self, attribute)
            if not isinstance(path, Path):
                raise TypeError(f"{attribute} は Path 型である必要があります。")
        if not self.code_hash:
            raise ValueError("code_hash は必須です。")
        if not self.data_hash:
            raise ValueError("data_hash は必須です。")

