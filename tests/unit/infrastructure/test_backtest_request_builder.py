from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from domain import ModelArtifact, ThetaParams
from infrastructure.backtest import BacktestPolicy, BacktestRequestFactory


def load_policy() -> BacktestPolicy:
    mapping = {
        "engine": {
            "timeframe": "1h",
            "dataset_root": "/data/canonical",
            "period": {"start": "2024-01-01T00:00:00Z", "end": "2024-02-01T00:00:00Z"},
            "cost_table_path": "/cfg/cost.yaml",
            "universe_path": "/cfg/universe.yaml",
        },
        "entry_rule": {"value": {"use_theta": True}},
        "exit_rule": {"value": {"max_bars": 24}},
        "costs": {"value": {"commission_bps": 10}},
        "evaluation": {
            "value": {
                "min_sharpe": 1.2,
                "max_drawdown": 0.1,
                "min_trades": 100,
                "max_halt_rate": 0.4,
            }
        },
        "stress": {"value": {"vol_spike": [1.5]}},
    }
    return BacktestPolicy.from_mapping(mapping)


def make_artifact(tmp_path: Path) -> ModelArtifact:
    dummy_path = tmp_path / "model.bin"
    dummy_path.write_bytes(b"test")
    now = datetime.now(timezone.utc)
    return ModelArtifact(
        model_version="model-001",
        created_at=now,
        created_by="tests",
        ai1_path=dummy_path,
        ai2_path=dummy_path,
        feature_schema_path=dummy_path,
        params_path=dummy_path,
        metrics_path=dummy_path,
        code_hash="code",
        data_hash="data",
    )


def test_backtest_request_factory_builds_request(tmp_path: Path) -> None:
    factory = BacktestRequestFactory(policy=load_policy())
    artifact = make_artifact(tmp_path)
    theta = ThetaParams(theta1=0.7, theta2=0.3, updated_at=datetime.now(timezone.utc), updated_by="tests")

    request = factory.build(artifact=artifact, theta_params=theta)

    assert request.params["theta1"] == theta.theta1
    assert request.engine_config["dataset_root"] == "/data/canonical"
    assert request.stress_scenarios[0].name == "vol_spike"

