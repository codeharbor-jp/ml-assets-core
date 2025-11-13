from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pytest

from domain import ModelArtifact, ThetaParams
from infrastructure.databases.postgres import PostgresConfig, PostgresPoolConfig
from infrastructure.repositories.model_registry import (
    PostgresAuditLogger,
    PostgresMetricsRepository,
    PostgresRegistryUpdater,
    _build_registry_params,
)


class DummyConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[Any, Mapping[str, Any] | None]] = []
        self.committed = False
        self.rolled_back = False

    def execute(self, query: Any, params: Mapping[str, Any] | None = None) -> None:
        self.executed.append((query, params or {}))

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class DummyConnectionContext:
    def __init__(self, connection: DummyConnection) -> None:
        self._connection = connection

    def __enter__(self) -> DummyConnection:
        return self._connection

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class DummyPool:
    def __init__(self) -> None:
        self.connection_instance = DummyConnection()

    def connection(self) -> DummyConnectionContext:
        return DummyConnectionContext(self.connection_instance)

    def close(self) -> None:
        pass

    def wait_close(self, timeout) -> None:  # noqa: D401 - pool interface準拠
        pass


def make_config() -> PostgresConfig:
    mapping = {
        "dsn": "postgresql://example",
        "pool": {"min_size": 1, "max_size": 4, "timeout_seconds": 5},
        "statement_timeout_ms": 1000,
        "search_path": ["core", "audit", "public"],
        "schemas": {"core": "core", "audit": "audit"},
    }
    return PostgresConfig.from_mapping(mapping)


def test_postgres_pool_config_validation() -> None:
    config = PostgresPoolConfig.from_mapping({"min_size": 1, "max_size": 5, "timeout_seconds": 3})
    assert config.min_size == 1
    assert config.max_size == 5
    assert config.timeout_seconds == 3.0

    with pytest.raises(ValueError):
        PostgresPoolConfig.from_mapping({"min_size": 0, "max_size": 5, "timeout_seconds": 3})


def test_postgres_config_from_mapping() -> None:
    config = make_config()
    assert config.dsn == "postgresql://example"
    assert config.pool.max_size == 4
    assert config.statement_timeout_ms == 1000
    assert config.search_path == ("core", "audit", "public")
    assert config.core_schema == "core"
    assert config.audit_schema == "audit"


def test_metrics_repository_persists_each_metric() -> None:
    config = make_config()
    pool = DummyPool()

    def pool_factory(_: PostgresConfig) -> DummyPool:
        return pool

    from infrastructure.databases.postgres import PostgresConnectionProvider

    provider = PostgresConnectionProvider(config, pool_factory=pool_factory)
    repo = PostgresMetricsRepository(connection_provider=provider)

    repo.store("model-1", {"metric_a": 0.8, "metric_b": 1.2})

    connection = pool.connection_instance
    assert connection.committed is True
    executed_params = [params for _, params in connection.executed]
    assert len(executed_params) == 2
    assert executed_params[0]["model_version"] == "model-1"
    assert executed_params[0]["metric_name"] == "metric_a"


def test_registry_updater_inserts_and_audits() -> None:
    config = make_config()
    pool = DummyPool()

    def pool_factory(_: PostgresConfig) -> DummyPool:
        return pool

    from infrastructure.databases.postgres import PostgresConnectionProvider

    provider = PostgresConnectionProvider(config, pool_factory=pool_factory)
    updater = PostgresRegistryUpdater(connection_provider=provider)

    artifact = ModelArtifact(
        model_version="v1",
        created_at=datetime.now(timezone.utc),
        created_by="tester",
        ai1_path=Path("/tmp/ai1"),
        ai2_path=Path("/tmp/ai2"),
        feature_schema_path=Path("/tmp/schema.json"),
        params_path=Path("/tmp/params.yaml"),
        metrics_path=Path("/tmp/metrics.json"),
        code_hash="abc",
        data_hash="def",
    )
    theta = ThetaParams(theta1=0.7, theta2=0.3, updated_at=datetime.now(timezone.utc), updated_by="tester")

    event_id = updater.update(artifact, theta)
    assert event_id

    connection = pool.connection_instance
    assert connection.committed is True
    assert len(connection.executed) == 2
    assert connection.executed[0][1]["model_version"] == "v1"
    assert connection.executed[1][1]["model_version"] == "v1"


def test_audit_logger_records_event() -> None:
    config = make_config()
    pool = DummyPool()

    def pool_factory(_: PostgresConfig) -> DummyPool:
        return pool

    from infrastructure.databases.postgres import PostgresConnectionProvider

    provider = PostgresConnectionProvider(config, pool_factory=pool_factory)
    audit_logger = PostgresAuditLogger(connection_provider=provider, event_type="retrain")

    audit_logger.log("learning.completed", {"model_version": "v1"})

    connection = pool.connection_instance
    assert connection.committed is True
    assert connection.executed[0][1]["event_name"] == "learning.completed"


def test_build_registry_params_contains_expected_fields() -> None:
    artifact = ModelArtifact(
        model_version="v1",
        created_at=datetime.now(timezone.utc),
        created_by="tester",
        ai1_path=Path("/tmp/ai1"),
        ai2_path=Path("/tmp/ai2"),
        feature_schema_path=Path("/tmp/schema.json"),
        params_path=Path("/tmp/params.yaml"),
        metrics_path=Path("/tmp/metrics.json"),
        code_hash="abc",
        data_hash="def",
        notes="note",
    )
    theta = ThetaParams(theta1=0.6, theta2=0.4, updated_at=datetime.now(timezone.utc), updated_by="tester")

    params = _build_registry_params(artifact, theta, status="deployed")
    assert params["model_version"] == "v1"
    assert params["theta1"] == 0.6
    assert params["notes"] == "note"

