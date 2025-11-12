"""
アプリケーション全体の初期化を担うDIコンテナ。

要件書の原則に従い、設定値は必ず YAML から読み込まれ、コード側で
フォールバックを持たない。DI コンテナは設定ロード、ロギング初期化、
メトリクス初期化を統括し、利用側には初期化済みのコンテキストを返す。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol


class ConfigLoader(Protocol):
    """設定ファイル群を読み込み、検証済みの構成を返すインターフェース。"""

    def load(self) -> "ConfigBundle":
        raise NotImplementedError


class LoggingConfigurator(Protocol):
    """ロギング設定を適用するインターフェース。"""

    def configure(self, config: Mapping[str, Any]) -> None:
        raise NotImplementedError


class MetricsConfigurator(Protocol):
    """メトリクス・トレーシングの初期化を行うインターフェース。"""

    def configure(self, config: Mapping[str, Any]) -> None:
        raise NotImplementedError


class BootstrapError(RuntimeError):
    """ブートストラップ処理でのエラーを表す基底例外。"""


class MissingConfigurationError(BootstrapError):
    """必須設定が欠落している場合の例外。"""


class InvalidConfigurationError(BootstrapError):
    """設定値が期待する形式ではない場合の例外。"""


@dataclass(frozen=True)
class ConfigBundle:
    """設定 YAML から構築された辞書ラッパー。"""

    root: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """設定の浅いコピーを返す。"""

        return dict(self.root)

    def require_section(self, section: str) -> Mapping[str, Any]:
        """
        指定セクションの存在と型を検証して返す。

        Args:
            section: 取得したい設定セクション名。

        Returns:
            Mapping[str, Any]: セクション内容。

        Raises:
            MissingConfigurationError: セクションが存在しない場合。
            InvalidConfigurationError: セクションがマッピングではない場合。
        """

        if section not in self.root:
            raise MissingConfigurationError(f"設定セクション '{section}' が存在しません。")

        value = self.root[section]
        if not isinstance(value, Mapping):
            raise InvalidConfigurationError(
                f"設定セクション '{section}' は Mapping である必要があります。"
            )
        return value

    def require_value(self, section: str, key: str) -> Any:
        """
        指定セクション内のキーの存在と値を検証して返す。

        Raises:
            MissingConfigurationError: キーが存在しない場合。
        """

        mapping = self.require_section(section)
        if key not in mapping:
            raise MissingConfigurationError(f"設定キー '{section}.{key}' が存在しません。")
        return mapping[key]


@dataclass(frozen=True)
class BootstrapContext:
    """
    ブートストラップ処理後に利用側へ渡すコンテキスト。

    現時点では設定バンドルのみを保持するが、今後の拡張で依存関係を追加する。
    """

    config: ConfigBundle


@dataclass
class BootstrapContainer:
    """
    アプリケーション全体の初期化を司るコンテナ。

    Attributes:
        project_root: プロジェクトのルートパス。
        config_loader_factory: ConfigLoader を生成するファクトリ。
        logging_configurator: ロギング設定適用オブジェクト。
        metrics_configurator: メトリクス設定適用オブジェクト。
    """

    project_root: Path
    config_loader_factory: Callable[[Path], ConfigLoader]
    logging_configurator: LoggingConfigurator
    metrics_configurator: MetricsConfigurator

    def initialize(self) -> BootstrapContext:
        """
        設定ロード・ロギング初期化・メトリクス初期化を順に実行する。

        Returns:
            BootstrapContext: 初期化済みのコンテキスト。

        Raises:
            BootstrapError: 初期化過程での検証エラー。
        """

        config_loader = self.config_loader_factory(self.project_root)
        config_bundle = config_loader.load()

        logging_config = config_bundle.require_section("logging")
        metrics_config = config_bundle.require_section("metrics")

        self.logging_configurator.configure(logging_config)
        self.metrics_configurator.configure(metrics_config)

        return BootstrapContext(config=config_bundle)

