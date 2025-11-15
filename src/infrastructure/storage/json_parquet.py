"""
Parquet 互換操作を簡易的な JSON シリアライゼーションで代替するユーティリティ。

本番では pyarrow 等の実パーサを利用することを想定しているが、現段階では軽量な
依存で単体テストを成立させる目的で JSON 形式を採用している。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence

from .storage_client import StorageError


class JsonParquetReader:
    """
    `ParquetReader` プロトコルに準拠した JSON ベースの簡易リーダー。
    """

    def read(self, path: Path) -> Sequence[Mapping[str, object]]:
        try:
            with Path(path).open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise StorageError(f"JSON の解析に失敗しました: {path}") from exc

        if not isinstance(data, list):
            raise StorageError(f"Parquet(代替)ファイルの形式が不正です: {path}")

        normalized: list[Mapping[str, object]] = []
        for entry in data:
            if not isinstance(entry, dict):
                raise StorageError(f"Parquet(代替)ファイルの要素がオブジェクトではありません: {path}")
            normalized.append({key: _coerce_value(value) for key, value in entry.items()})

        return normalized


class JsonParquetWriter:
    """
    `ParquetWriter` プロトコルに準拠した JSON ベースの簡易ライター。
    """

    def write(self, path: Path, rows: Sequence[Mapping[str, object]]) -> None:
        serializable = [dict(row) for row in rows]
        with Path(path).open("w", encoding="utf-8") as handle:
            json.dump(serializable, handle, ensure_ascii=False, indent=2, sort_keys=True)


def _coerce_value(value: object) -> object:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return value
    raise StorageError(f"数値以外の値を float に変換できません: {value!r}")

