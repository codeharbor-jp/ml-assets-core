"""
PostgreSQL 接続ユーティリティ。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, ContextManager, Mapping, Sequence, cast

from psycopg import sql
from psycopg_pool import ConnectionPool


class DatabaseOperationError(RuntimeError):
    """データベース操作が失敗した際に送出される例外。"""


@dataclass(frozen=True)
class PostgresPoolConfig:
    """
    コネクションプール設定。
    """

    min_size: int
    max_size: int
    timeout_seconds: float

    @staticmethod
    def from_mapping(mapping: Mapping[str, object]) -> "PostgresPoolConfig":
        try:
            min_size = _to_int(mapping["min_size"], name="pool.min_size")
            max_size = _to_int(mapping["max_size"], name="pool.max_size")
            timeout_seconds = _to_float(mapping.get("timeout_seconds", 5), name="pool.timeout_seconds")
        except KeyError as exc:
            raise ValueError(f"pool 設定に必須キー {exc!s} が存在しません。") from exc

        if min_size <= 0 or max_size <= 0:
            raise ValueError("pool.min_size と pool.max_size は正の値である必要があります。")
        if min_size > max_size:
            raise ValueError("pool.min_size は pool.max_size 以下である必要があります。")
        if timeout_seconds <= 0:
            raise ValueError("pool.timeout_seconds は正の値である必要があります。")

        return PostgresPoolConfig(min_size=min_size, max_size=max_size, timeout_seconds=timeout_seconds)


@dataclass(frozen=True)
class PostgresConfig:
    """
    PostgreSQL 接続設定。
    """

    dsn: str
    pool: PostgresPoolConfig
    statement_timeout_ms: int
    search_path: tuple[str, ...]
    core_schema: str
    audit_schema: str

    @staticmethod
    def from_mapping(mapping: Mapping[str, object]) -> "PostgresConfig":
        try:
            dsn_raw = mapping["dsn"]
        except KeyError as exc:
            raise ValueError("postgres 設定に dsn が存在しません。") from exc

        if dsn_raw in (None, ""):
            raise ValueError("postgres.dsn は環境設定で必須です。")
        dsn = str(dsn_raw)

        pool_mapping = cast(Mapping[str, object], mapping.get("pool", {}))
        if not pool_mapping:
            raise ValueError("postgres.pool 設定が存在しません。")

        pool = PostgresPoolConfig.from_mapping(pool_mapping)

        statement_timeout_ms = _to_int(mapping.get("statement_timeout_ms", 30000), name="statement_timeout_ms")
        if statement_timeout_ms <= 0:
            raise ValueError("statement_timeout_ms は正の値である必要があります。")

        search_path_raw = cast(Sequence[object], mapping.get("search_path", ("public",)))
        if not search_path_raw:
            raise ValueError("search_path は少なくとも1つのスキーマを指定する必要があります。")
        search_path = tuple(str(part) for part in search_path_raw)

        schemas_mapping = cast(Mapping[str, object], mapping.get("schemas", {}))
        core_schema = str(schemas_mapping.get("core", "core"))
        audit_schema = str(schemas_mapping.get("audit", "audit"))

        return PostgresConfig(
            dsn=dsn,
            pool=pool,
            statement_timeout_ms=statement_timeout_ms,
            search_path=search_path,
            core_schema=core_schema,
            audit_schema=audit_schema,
        )


class PostgresConnectionProvider:
    """
    psycopg の ConnectionPool をラップした接続プロバイダ。
    """

    def __init__(
        self,
        config: PostgresConfig,
        *,
        pool_factory: Callable[[PostgresConfig], ConnectionPool] | None = None,
    ) -> None:
        self._config = config
        self._pool_factory = pool_factory or _default_pool_factory
        self._pool = self._pool_factory(config)

    @property
    def config(self) -> PostgresConfig:
        return self._config

    def connection(self) -> ContextManager[Any]:
        """
        コネクションプールから接続を取得するコンテキストマネージャを返す。
        """

        return self._pool.connection()

    def close(self) -> None:
        """
        コネクションプールをクローズする。
        """

        self._pool.close()


def _default_pool_factory(config: PostgresConfig) -> ConnectionPool:
    """
    psycopg の ConnectionPool を生成するデフォルト実装。
    """

    def _configure(conn: Any) -> None:
        if config.search_path:
            search_sql = sql.SQL(", ").join(sql.Identifier(part) for part in config.search_path)
            conn.execute(sql.SQL("SET search_path TO {}").format(search_sql))
        if config.statement_timeout_ms:
            conn.execute("SET statement_timeout TO %s", (f"{config.statement_timeout_ms}ms",))

    return ConnectionPool(
        conninfo=config.dsn,
        min_size=config.pool.min_size,
        max_size=config.pool.max_size,
        timeout=config.pool.timeout_seconds,
        configure=_configure,
    )


def _to_int(value: object, *, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} は真偽値ではなく整数を指定してください。")
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        return int(value)
    raise ValueError(f"{name} は整数値で指定してください。")


def _to_float(value: object, *, name: str) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value)
    raise ValueError(f"{name} は数値で指定してください。")

