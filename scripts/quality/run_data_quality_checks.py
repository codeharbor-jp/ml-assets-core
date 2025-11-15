#!/usr/bin/env python3
"""データ品質検証を実行する CLI スクリプト。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence

import yaml

from quality import DQExpectations, ValidationError, validate_dataset


def _load_dataset(path: Path) -> Sequence[Mapping[str, object]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"データセットのJSON読み込みに失敗しました: {path}") from exc

    if not isinstance(data, list):
        raise ValueError(f"データセットはJSON配列である必要があります: {path}")

    rows: list[Mapping[str, object]] = []
    for index, entry in enumerate(data):
        if not isinstance(entry, Mapping):
            raise ValueError(f"データセットの要素がオブジェクトではありません (index={index})")
        rows.append(dict(entry))
    return rows


def _load_expectations(path: Path) -> DQExpectations:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"期待値YAMLの読み込みに失敗しました: {path}") from exc

    if not isinstance(raw, Mapping):
        raise ValueError(f"期待値YAMLの形式が不正です: {path}")
    return DQExpectations.from_mapping(raw)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="データ品質チェックを実行します。")
    parser.add_argument("--dataset", required=True, type=Path, help="検証対象のJSONデータセットパス")
    parser.add_argument(
        "--expectations",
        required=True,
        type=Path,
        help="期待値を記述したYAMLファイルのパス",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    dataset_path: Path = args.dataset
    expectations_path: Path = args.expectations

    rows = _load_dataset(dataset_path)
    expectations = _load_expectations(expectations_path)

    try:
        validate_dataset(rows, expectations)
    except ValidationError as exc:
        print(f"[DQ][ERROR] {exc}", file=sys.stderr)
        return 1

    print(
        f"[DQ][OK] dataset={expectations.name} rows={len(rows)} min_rows={expectations.min_rows} "
        f"max_missing_rate={expectations.max_missing_rate:.2%}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI エントリポイント
    sys.exit(main())
