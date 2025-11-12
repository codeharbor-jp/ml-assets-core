"""
メトリクス初期化ロジック。
"""

from __future__ import annotations

from typing import Any, Mapping

from .container import InvalidConfigurationError, MetricsConfigurator


class MetricsConfiguratorRegistry(MetricsConfigurator):
    """
    provider 名に応じて委譲するディスパッチャ。
    """

    def __init__(self, delegates: Mapping[str, MetricsConfigurator]) -> None:
        if not delegates:
            raise ValueError("メトリクス設定の委譲先が定義されていません。")
        self._delegates = dict(delegates)

    def configure(self, config: Mapping[str, Any]) -> None:
        provider = _require_string(config, "provider")
        delegate = self._delegates.get(provider)
        if delegate is None:
            raise InvalidConfigurationError(
                f"metrics provider '{provider}' に対応する初期化ロジックが見つかりません。"
            )
        delegate.configure(config)


class NoopMetricsConfigurator(MetricsConfigurator):
    """
    provider == noop の場合に適用するダミー実装。
    """

    EXPECTED_PROVIDER = "noop"

    def configure(self, config: Mapping[str, Any]) -> None:
        provider = _require_string(config, "provider")
        if provider != self.EXPECTED_PROVIDER:
            raise InvalidConfigurationError(
                f"provider '{provider}' は NoopMetricsConfigurator では扱えません。"
            )
        # noop: テストやローカル開発でメトリクス初期化をスキップする場合に使用する。


def _require_string(config: Mapping[str, Any], key: str) -> str:
    if key not in config:
        raise InvalidConfigurationError(f"metrics 設定に '{key}' が存在しません。")
    value = config[key]
    if not isinstance(value, str) or not value:
        raise InvalidConfigurationError(f"metrics 設定の '{key}' は非空の str である必要があります。")
    return value

