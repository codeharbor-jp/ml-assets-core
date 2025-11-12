"""
設定 YAML 群を読み込み、検証済みの ConfigBundle を生成するローダ。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

import yaml
from pydantic import BaseModel, Extra, ValidationError

from .container import (
    ConfigBundle,
    ConfigLoader,
    InvalidConfigurationError,
    MissingConfigurationError,
)


class LoggingConfigModel(BaseModel):
    """logging 設定の最小検証モデル。"""

    version: int

    class Config:
        extra = Extra.allow


class MetricsConfigModel(BaseModel):
    """metrics 設定の最小検証モデル。"""

    provider: str

    class Config:
        extra = Extra.allow


class AppConfigModel(BaseModel):
    """
    アプリケーション全体の設定バリデーション。

    必須セクション（logging, metrics）の存在と最低限の構造のみを検証し、
    その他のセクションは追加情報として保持する。
    """

    logging: LoggingConfigModel
    metrics: MetricsConfigModel

    class Config:
        extra = Extra.allow


class YamlConfigLoader(ConfigLoader):
    """
    `configs/base` と `configs/envs/<env>` の YAML をロードしマージする実装。
    """

    def __init__(
        self,
        project_root: Path,
        *,
        environment: str | None = None,
        configs_dir_name: str = "configs",
    ) -> None:
        self._project_root = project_root.resolve()
        self._configs_root = self._project_root / configs_dir_name
        self._environment = environment or os.getenv("SERVICE_ENV")

    def load(self) -> ConfigBundle:
        env = self._environment
        if not env:
            raise MissingConfigurationError(
                "環境変数 'SERVICE_ENV' が未設定のため、設定をロードできません。"
            )

        base_dir = self._configs_root / "base"
        env_dir = self._configs_root / "envs" / env

        self._ensure_directory(base_dir, description="基本設定ディレクトリ")
        self._ensure_directory(env_dir, description=f"環境設定ディレクトリ ({env})")

        base_config = self._load_directory(base_dir)
        env_config = self._load_directory(env_dir)
        _validate_overlay_keys(base_config, env_config)
        merged = _deep_merge(base_config, env_config)

        try:
            validated = AppConfigModel(**merged)
        except ValidationError as exc:
            raise InvalidConfigurationError("設定値の検証に失敗しました。") from exc

        return ConfigBundle(root=validated.dict())

    def _load_directory(self, directory: Path) -> dict[str, Any]:
        yaml_files = sorted(
            {p for p in directory.glob("**/*.yml")} | {p for p in directory.glob("**/*.yaml")}
        )

        if not yaml_files:
            raise MissingConfigurationError(
                f"{directory} に YAML ファイルが存在しません。"
            )

        accumulator: dict[str, Any] = {}
        for file_path in yaml_files:
            data = self._load_yaml(file_path)
            accumulator = _deep_merge(accumulator, data)
        return accumulator

    def _load_yaml(self, file_path: Path) -> Mapping[str, Any]:
        try:
            with file_path.open("r", encoding="utf-8") as fh:
                content = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise InvalidConfigurationError(f"YAML の解析に失敗しました: {file_path}") from exc

        if content is None:
            raise InvalidConfigurationError(f"YAML ファイルが空です: {file_path}")

        if not isinstance(content, Mapping):
            raise InvalidConfigurationError(
                f"YAML ファイルのトップレベルは Mapping である必要があります: {file_path}"
            )

        return content

    @staticmethod
    def _ensure_directory(directory: Path, *, description: str) -> None:
        if not directory.exists():
            raise MissingConfigurationError(f"{description} ({directory}) が存在しません。")
        if not directory.is_dir():
            raise MissingConfigurationError(f"{description} ({directory}) がディレクトリではありません。")


def _deep_merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    """
    ネストされた辞書をマージする。overlay の値が優先される。
    """

    result: dict[str, Any] = dict(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], Mapping) and isinstance(value, Mapping):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _validate_overlay_keys(base: Mapping[str, Any], overlay: Mapping[str, Any], *, path: str = "") -> None:
    """
    環境差分で未定義キーが追加されていないか検証する。
    """

    for key, value in overlay.items():
        if key not in base:
            raise InvalidConfigurationError(
                f"環境差分で未定義の設定キー '{path}{key}' が検出されました。"
                " 先に configs/base 配下へ定義を追加してください。"
            )

        base_value = base[key]
        if isinstance(value, Mapping) and isinstance(base_value, Mapping):
            _validate_overlay_keys(base_value, value, path=f"{path}{key}.")
        elif isinstance(value, Mapping) and not isinstance(base_value, Mapping):
            raise InvalidConfigurationError(
                f"設定キー '{path}{key}' は base では非マッピング型ですが、環境差分で Mapping が指定されました。"
            )

