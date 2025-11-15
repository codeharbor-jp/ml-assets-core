from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


class ValidationError(Exception):
    """データ品質検証で条件を満たさなかった場合に送出される例外。"""


@dataclass(frozen=True)
class DQExpectations:
    """データ品質検証で利用する期待値。"""

    name: str
    required_columns: Sequence[str]
    min_rows: int
    max_missing_rate: float
    column_ranges: Mapping[str, tuple[float | None, float | None]]

    @staticmethod
    def from_mapping(mapping: Mapping[str, object]) -> "DQExpectations":
        name = str(mapping.get("name", "dataset"))
        required_columns = tuple(str(col) for col in mapping.get("required_columns", []))
        min_rows = int(mapping.get("min_rows", 1))
        max_missing_rate = float(mapping.get("max_missing_rate", 0.0))

        raw_ranges = mapping.get("column_ranges", {})
        column_ranges: dict[str, tuple[float | None, float | None]] = {}
        if isinstance(raw_ranges, Mapping):
            for column, raw_range in raw_ranges.items():
                if not isinstance(raw_range, Sequence) or len(raw_range) != 2:
                    raise ValueError(f"column_ranges[{column}] は [min, max] の形式で指定してください。")
                min_value = _to_optional_float(raw_range[0])
                max_value = _to_optional_float(raw_range[1])
                column_ranges[str(column)] = (min_value, max_value)
        else:
            raise ValueError("column_ranges は Mapping である必要があります。")

        return DQExpectations(
            name=name,
            required_columns=required_columns,
            min_rows=min_rows,
            max_missing_rate=max_missing_rate,
            column_ranges=column_ranges,
        )


def validate_dataset(rows: Sequence[Mapping[str, object]], expectations: DQExpectations) -> None:
    """期待値に基づいてデータ品質を検証する。"""

    if len(rows) < expectations.min_rows:
        raise ValidationError(
            f"{expectations.name}: 行数 {len(rows)} が最小行数 {expectations.min_rows} を下回っています。"
        )

    missing_rates = _compute_missing_rates(rows, expectations.required_columns)
    for column, rate in missing_rates.items():
        if rate > expectations.max_missing_rate:
            raise ValidationError(
                f"{expectations.name}: カラム {column} の欠損率 {rate:.2%} が許容値 "
                f"{expectations.max_missing_rate:.2%} を超えています。"
            )

    violations = list(_iter_range_violations(rows, expectations.column_ranges))
    if violations:
        messages = ", ".join(violations)
        raise ValidationError(f"{expectations.name}: 値の範囲逸脱が検出されました: {messages}")


def _compute_missing_rates(
    rows: Sequence[Mapping[str, object]],
    required_columns: Sequence[str],
) -> Mapping[str, float]:
    if not rows:
        return {column: 1.0 for column in required_columns}

    totals = {column: 0 for column in required_columns}
    missing = {column: 0 for column in required_columns}

    for row in rows:
        for column in required_columns:
            totals[column] += 1
            if _is_missing(row.get(column)):
                missing[column] += 1

    return {column: missing[column] / max(totals[column], 1) for column in required_columns}


def _iter_range_violations(
    rows: Sequence[Mapping[str, object]],
    column_ranges: Mapping[str, tuple[float | None, float | None]],
) -> Iterable[str]:
    for index, row in enumerate(rows):
        for column, (min_value, max_value) in column_ranges.items():
            value = row.get(column)
            if value is None:
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue

            if min_value is not None and numeric < min_value:
                yield f"row={index} column={column} value={numeric} < min={min_value}"
            if max_value is not None and numeric > max_value:
                yield f"row={index} column={column} value={numeric} > max={max_value}"


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _to_optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"値 {value!r} を float に変換できません。") from exc
