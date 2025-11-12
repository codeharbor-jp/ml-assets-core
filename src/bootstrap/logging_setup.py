"""
ロギング初期化ロジック。
"""

from __future__ import annotations

import logging.config
from typing import Any, Mapping

from .container import InvalidConfigurationError, LoggingConfigurator


class DictConfigLoggingConfigurator(LoggingConfigurator):
    """
    標準ライブラリの ``logging.config.dictConfig`` を用いたロギング初期化。
    """

    def configure(self, config: Mapping[str, Any]) -> None:
        if "version" not in config:
            raise InvalidConfigurationError("logging 設定に 'version' が存在しません。")

        try:
            logging.config.dictConfig(_to_plain_dict(config))
        except (ValueError, TypeError, AttributeError) as exc:
            raise InvalidConfigurationError("logging 設定の適用に失敗しました。") from exc


def _to_plain_dict(mapping: Mapping[str, Any]) -> dict[str, Any]:
    """
    ネストされた Mapping を標準の dict に変換するヘルパー。
    """

    result: dict[str, Any] = {}
    for key, value in mapping.items():
        if isinstance(value, Mapping):
            result[key] = _to_plain_dict(value)
        else:
            result[key] = value
    return result

