"""
設定リポジトリ関連の例外定義。
"""

from __future__ import annotations


class ConfigRepositoryError(RuntimeError):
    """設定リポジトリが発生させる基底例外。"""


class ConfigNotFoundError(ConfigRepositoryError):
    """要求された設定ファイルが存在しない。"""


class SchemaValidationError(ConfigRepositoryError):
    """スキーマ検証に失敗した。"""

