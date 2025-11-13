"""
PostgreSQL を用いたモデルレジストリ関連リポジトリ。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Protocol, cast
from uuid import uuid4

from psycopg import sql

from application.services.trainer import MetricsRepository
from application.usecases.learning import AuditLogger
from application.usecases.publish import RegistryUpdater
from domain import ModelArtifact, ThetaParams
from infrastructure.databases import DatabaseOperationError, PostgresConnectionProvider


class _SyncConnection(Protocol):
    def execute(self, query, params=None) -> object:  # pragma: no cover - Protocolのみ
        ...

    def commit(self) -> None:  # pragma: no cover - Protocolのみ
        ...

    def rollback(self) -> None:  # pragma: no cover - Protocolのみ
        ...


@dataclass
class PostgresMetricsRepository(MetricsRepository):
    """
    学習メトリクスを PostgreSQL に保存するリポジトリ。
    """

    connection_provider: PostgresConnectionProvider

    def __post_init__(self) -> None:
        core_schema = self.connection_provider.config.core_schema
        self._table = sql.SQL("{}.{}").format(sql.Identifier(core_schema), sql.Identifier("training_metrics"))
        self._insert_sql = sql.SQL(
            """
            INSERT INTO {table} (
                model_version,
                metric_name,
                metric_value,
                recorded_at
            ) VALUES (
                %(model_version)s,
                %(metric_name)s,
                %(metric_value)s,
                %(recorded_at)s
            )
            ON CONFLICT (model_version, metric_name)
            DO UPDATE SET
                metric_value = EXCLUDED.metric_value,
                recorded_at = EXCLUDED.recorded_at
            """
        ).format(table=self._table)

    def store(self, model_version: str, metrics: Mapping[str, float]) -> None:
        if not metrics:
            return

        with self.connection_provider.connection() as conn:
            connection = cast(_SyncConnection, conn)
            try:
                for name, value in metrics.items():
                    params = {
                        "model_version": model_version,
                        "metric_name": name,
                        "metric_value": float(value),
                        "recorded_at": datetime.now(timezone.utc),
                    }
                    connection.execute(self._insert_sql, params)
                connection.commit()
            except Exception as exc:  # pragma: no cover - エラーパス
                connection.rollback()
                raise DatabaseOperationError("学習メトリクスの保存に失敗しました。") from exc


@dataclass
class PostgresRegistryUpdater(RegistryUpdater):
    """
    モデルレジストリを PostgreSQL で更新する実装。
    """

    connection_provider: PostgresConnectionProvider
    default_status: str = "deployed"

    def __post_init__(self) -> None:
        cfg = self.connection_provider.config
        self._registry_table = sql.SQL("{}.{}").format(sql.Identifier(cfg.core_schema), sql.Identifier("model_registry"))
        self._audit_table = sql.SQL("{}.{}").format(sql.Identifier(cfg.audit_schema), sql.Identifier("model_registry_events"))

        self._upsert_registry_sql = sql.SQL(
            """
            INSERT INTO {table} (
                model_version,
                status,
                created_at,
                created_by,
                ai1_path,
                ai2_path,
                feature_schema_path,
                params_path,
                metrics_path,
                code_hash,
                data_hash,
                theta1,
                theta2,
                theta_updated_at,
                theta_updated_by,
                theta_source_model_version,
                notes
            )
            VALUES (
                %(model_version)s,
                %(status)s,
                %(created_at)s,
                %(created_by)s,
                %(ai1_path)s,
                %(ai2_path)s,
                %(feature_schema_path)s,
                %(params_path)s,
                %(metrics_path)s,
                %(code_hash)s,
                %(data_hash)s,
                %(theta1)s,
                %(theta2)s,
                %(theta_updated_at)s,
                %(theta_updated_by)s,
                %(theta_source_model_version)s,
                %(notes)s
            )
            ON CONFLICT (model_version) DO UPDATE SET
                status = EXCLUDED.status,
                ai1_path = EXCLUDED.ai1_path,
                ai2_path = EXCLUDED.ai2_path,
                feature_schema_path = EXCLUDED.feature_schema_path,
                params_path = EXCLUDED.params_path,
                metrics_path = EXCLUDED.metrics_path,
                code_hash = EXCLUDED.code_hash,
                data_hash = EXCLUDED.data_hash,
                theta1 = EXCLUDED.theta1,
                theta2 = EXCLUDED.theta2,
                theta_updated_at = EXCLUDED.theta_updated_at,
                theta_updated_by = EXCLUDED.theta_updated_by,
                theta_source_model_version = EXCLUDED.theta_source_model_version,
                notes = EXCLUDED.notes,
                updated_at = NOW()
            """
        ).format(table=self._registry_table)

        self._insert_audit_sql = sql.SQL(
            """
            INSERT INTO {table} (
                event_id,
                model_version,
                event_type,
                payload,
                created_at
            )
            VALUES (
                %(event_id)s,
                %(model_version)s,
                %(event_type)s,
                %(payload)s::jsonb,
                %(created_at)s
            )
            """
        ).format(table=self._audit_table)

    def update(self, artifact: ModelArtifact, theta_params: ThetaParams) -> str:
        event_id = str(uuid4())
        with self.connection_provider.connection() as conn:
            connection = cast(_SyncConnection, conn)
            try:
                registry_params = _build_registry_params(artifact, theta_params, status=self.default_status)
                connection.execute(self._upsert_registry_sql, registry_params)

                audit_payload = {
                    "status": self.default_status,
                    "theta": {
                        "theta1": theta_params.theta1,
                        "theta2": theta_params.theta2,
                        "updated_at": theta_params.updated_at.isoformat(),
                        "updated_by": theta_params.updated_by,
                        "source_model_version": theta_params.source_model_version,
                    },
                    "artifact": {
                        "model_version": artifact.model_version,
                        "code_hash": artifact.code_hash,
                        "data_hash": artifact.data_hash,
                    },
                }
                audit_params = {
                    "event_id": event_id,
                    "model_version": artifact.model_version,
                    "event_type": "publish",
                    "payload": json.dumps(audit_payload),
                    "created_at": datetime.now(timezone.utc),
                }
                connection.execute(self._insert_audit_sql, audit_params)

                connection.commit()
                return event_id
            except Exception as exc:  # pragma: no cover - エラーパス
                connection.rollback()
                raise DatabaseOperationError("モデルレジストリの更新に失敗しました。") from exc


@dataclass
class PostgresAuditLogger(AuditLogger):
    """
    汎用的な監査イベントロガー。
    """

    connection_provider: PostgresConnectionProvider
    event_type: str = "learning"

    def __post_init__(self) -> None:
        cfg = self.connection_provider.config
        self._audit_table = sql.SQL("{}.{}").format(sql.Identifier(cfg.audit_schema), sql.Identifier("ops_events"))
        self._insert_sql = sql.SQL(
            """
            INSERT INTO {table} (event_id, event_name, event_type, payload, created_at)
            VALUES (%(event_id)s, %(event_name)s, %(event_type)s, %(payload)s::jsonb, %(created_at)s)
            """
        ).format(table=self._audit_table)

    def log(self, event_name: str, payload: Mapping[str, str]) -> None:
        with self.connection_provider.connection() as conn:
            connection = cast(_SyncConnection, conn)
            try:
                params = {
                    "event_id": str(uuid4()),
                    "event_name": event_name,
                    "event_type": self.event_type,
                    "payload": json.dumps({str(k): str(v) for k, v in payload.items()}),
                    "created_at": datetime.now(timezone.utc),
                }
                connection.execute(self._insert_sql, params)
                connection.commit()
            except Exception as exc:  # pragma: no cover - エラーパス
                connection.rollback()
                raise DatabaseOperationError("監査イベントの記録に失敗しました。") from exc


def _build_registry_params(
    artifact: ModelArtifact,
    theta_params: ThetaParams,
    *,
    status: str,
) -> Mapping[str, object]:
    return {
        "model_version": artifact.model_version,
        "status": status,
        "created_at": artifact.created_at,
        "created_by": artifact.created_by,
        "ai1_path": str(artifact.ai1_path),
        "ai2_path": str(artifact.ai2_path),
        "feature_schema_path": str(artifact.feature_schema_path),
        "params_path": str(artifact.params_path),
        "metrics_path": str(artifact.metrics_path),
        "code_hash": artifact.code_hash,
        "data_hash": artifact.data_hash,
        "theta1": theta_params.theta1,
        "theta2": theta_params.theta2,
        "theta_updated_at": theta_params.updated_at,
        "theta_updated_by": theta_params.updated_by,
        "theta_source_model_version": theta_params.source_model_version,
        "notes": artifact.notes,
    }

