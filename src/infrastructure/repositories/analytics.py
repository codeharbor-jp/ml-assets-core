"""
PostgreSQL ベースの AnalyticsRepository 実装。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from psycopg import sql

from application.services.analytics import AnalyticsRepository, MetricsQuery
from infrastructure.databases import DatabaseOperationError, PostgresConnectionProvider


_SYNC_CONNECTION = object


@dataclass
class PostgresAnalyticsRepository(AnalyticsRepository):
    """
    `analytics` スキーマ内のビュー / テーブルからメトリクスを取得する実装。

    想定テーブル:
      - {core_schema}.analytics_model_metrics (metric_name, metric_value, recorded_at)
      - {core_schema}.analytics_trading_metrics (pair_id, metric_name, metric_value, recorded_at)
      - {core_schema}.analytics_data_quality_metrics (metric_name, metric_value, recorded_at)
      - {core_schema}.analytics_risk_metrics (metric_name, metric_value, recorded_at)
    """

    connection_provider: PostgresConnectionProvider

    def fetch_model_metrics(self, query: MetricsQuery) -> Sequence[Mapping[str, float]]:
        table = self._table("analytics_model_metrics")
        sql_query, params = self._build_query(table, query)
        return self._execute(sql_query, params)

    def fetch_trading_metrics(self, query: MetricsQuery) -> Sequence[Mapping[str, float]]:
        table = self._table("analytics_trading_metrics")
        sql_query, params = self._build_query(table, query, include_pair_id=True)
        return self._execute(sql_query, params)

    def fetch_data_quality_metrics(self, query: MetricsQuery) -> Sequence[Mapping[str, float]]:
        table = self._table("analytics_data_quality_metrics")
        sql_query, params = self._build_query(table, query)
        return self._execute(sql_query, params)

    def fetch_risk_metrics(self, query: MetricsQuery) -> Sequence[Mapping[str, float]]:
        table = self._table("analytics_risk_metrics")
        sql_query, params = self._build_query(table, query)
        return self._execute(sql_query, params)

    def _table(self, name: str) -> sql.Composed:
        cfg = self.connection_provider.config
        return sql.SQL("{}.{}").format(sql.Identifier(cfg.core_schema), sql.Identifier(name))

    def _build_query(
        self,
        table: sql.Composed,
        query: MetricsQuery,
        *,
        include_pair_id: bool = False,
    ) -> tuple[sql.SQL, dict[str, object]]:
        base = sql.SQL(
            """
            SELECT metric_name, AVG(metric_value) AS value
            FROM {table}
            {where}
            GROUP BY metric_name
            ORDER BY metric_name ASC
            """
        )
        conditions: list[str] = []
        params: dict[str, object] = {}

        if query.start:
            conditions.append("recorded_at >= %(start)s")
            params["start"] = query.start
        if query.end:
            conditions.append("recorded_at <= %(end)s")
            params["end"] = query.end
        if include_pair_id and query.pair_id:
            conditions.append("pair_id = %(pair_id)s")
            params["pair_id"] = query.pair_id

        where_sql = sql.SQL("")
        if conditions:
            clause = " AND ".join(conditions)
            where_sql = sql.SQL("WHERE " + clause)

        final_sql = base.format(table=table, where=where_sql)
        return final_sql, params

    def _execute(self, statement: sql.SQL, params: Mapping[str, object]) -> Sequence[Mapping[str, float]]:
        try:
            with self.connection_provider.connection() as conn:
                cursor = conn.execute(statement, params)
                rows = cursor.fetchall()
        except Exception as exc:  # pragma: no cover - DB エラーはランタイム検出
            raise DatabaseOperationError("Analytics メトリクスの取得に失敗しました。") from exc

        results: list[dict[str, float]] = []
        for metric_name, value in rows:
            try:
                results.append({"metric": str(metric_name), "value": float(value)})
            except (TypeError, ValueError):
                continue
        return results

