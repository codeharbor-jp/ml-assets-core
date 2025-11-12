"""
設定ファイルを取得・検証するリポジトリ実装。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, cast

import yaml

from .exceptions import ConfigNotFoundError, ConfigRepositoryError, SchemaValidationError
from .schema_registry import SchemaRegistry

try:
    from jsonschema import Draft202012Validator, ValidationError
except ImportError as exc:  # pragma: no cover - 実行時に早期検知したい
    raise RuntimeError("jsonschema パッケージがインストールされていません。") from exc


def _ensure_mapping(data: object, *, origin: Path) -> Mapping[str, object]:
    if not isinstance(data, Mapping):
        raise ConfigRepositoryError(f"{origin} のトップレベルは Mapping である必要があります。")
    return cast(Mapping[str, object], data)


class ConfigRepository:
    """
    `configs/base` と `configs/envs/{env}` の YAML をマージし、スキーマ検証を行う。
    """

    def __init__(self, project_root: Path, schema_registry: SchemaRegistry) -> None:
        self._project_root = project_root.resolve()
        self._configs_root = self._project_root / "configs"
        self._schema_registry = schema_registry

    def load(self, name: str, *, environment: str) -> Mapping[str, object]:
        """
        指定された設定名称の YAML を読み込み、環境差分をマージして返す。

        Args:
            name: 設定ファイル名（拡張子なし）。例: `core_policy`
            environment: 使用する環境名（dev/stg/prod など）。

        Raises:
            ConfigNotFoundError: ファイルが存在しない場合。
            SchemaValidationError: スキーマ検証に失敗した場合。
        """

        base_path = self._configs_root / "base" / f"{name}.yaml"
        env_path = self._configs_root / "envs" / environment / f"{name}.yaml"

        if not base_path.exists():
            raise ConfigNotFoundError(f"ベース設定が存在しません: {base_path}")

        base_data = self._load_yaml(base_path)
        env_data = self._load_yaml(env_path) if env_path.exists() else {}

        merged = _deep_merge(base_data, env_data)
        schema = self._schema_registry.get_schema(name)

        if schema is not None:
            validator = Draft202012Validator(schema)
            try:
                validator.validate(merged)
            except ValidationError as exc:
                raise SchemaValidationError(
                    f"設定 '{name}' のスキーマ検証に失敗しました: {exc.message}"
                ) from exc

        return merged

    def _load_yaml(self, path: Path) -> Mapping[str, object]:
        if not path.exists():
            raise ConfigNotFoundError(f"設定ファイルが存在しません: {path}")
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise ConfigRepositoryError(f"YAML の解析に失敗しました: {path}") from exc

        if data is None:
            return {}
        return _ensure_mapping(data, origin=path)

    def dump(self, name: str, *, environment: str) -> str:
        """
        取得した設定を JSON 文字列で返す（監査ログなど向け）。
        """

        data = self.load(name, environment=environment)
        return json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)


def _deep_merge(base: Mapping[str, object], overlay: Mapping[str, object]) -> dict[str, object]:
    result = dict(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], Mapping) and isinstance(value, Mapping):
            base_nested = cast(Mapping[str, object], result[key])
            overlay_nested = cast(Mapping[str, object], value)
            result[key] = _deep_merge(base_nested, overlay_nested)
        else:
            result[key] = value
    return result

