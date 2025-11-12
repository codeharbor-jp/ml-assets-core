"""
設定スキーマを提供するレジストリ。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Mapping, Protocol

from .exceptions import ConfigNotFoundError


class SchemaRegistry(Protocol):
    """
    設定名に対応する JSON Schema を提供するインターフェース。
    """

    def get_schema(self, name: str) -> Mapping[str, object] | None:
        ...


class JsonSchemaRegistry(SchemaRegistry):
    """
    ディレクトリから JSON Schema を読み込むレジストリ。
    """

    def __init__(self, schema_root: Path) -> None:
        self._schema_root = schema_root.resolve()

    @lru_cache(maxsize=None)
    def get_schema(self, name: str) -> Mapping[str, object] | None:
        path = self._schema_root / f"{name}.json"
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except json.JSONDecodeError as exc:
            raise ConfigNotFoundError(f"スキーマ JSON の解析に失敗しました: {path}") from exc


class FlowSchemaRegistry(SchemaRegistry):
    """
    フロー内で一時的に定義されたスキーマを保持する簡易レジストリ。
    """

    def __init__(self) -> None:
        self._schemas: dict[str, Mapping[str, object]] = {}

    def register(self, name: str, schema: Mapping[str, object]) -> None:
        if not schema:
            raise ValueError("schema は空にできません。")
        self._schemas[name] = schema

    def get_schema(self, name: str) -> Mapping[str, object] | None:
        return self._schemas.get(name)

