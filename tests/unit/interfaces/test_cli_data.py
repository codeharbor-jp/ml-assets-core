from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from interfaces.cli.app import create_cli

runner = CliRunner()


@pytest.fixture()
def dataset_file(tmp_path: Path) -> Path:
    data = [
        {"timestamp": "2025-01-01T00:00:00Z", "close": 1.0, "volume": 100},
        {"timestamp": "2025-01-01T01:00:00Z", "close": 1.01, "volume": 110},
    ]
    target = tmp_path / "dataset.json"
    target.write_text(json.dumps(data), encoding="utf-8")
    return target


@pytest.fixture()
def expectations_file(tmp_path: Path) -> Path:
    content = (
        "name: tmp\n"
        "required_columns: [timestamp, close]\n"
        "min_rows: 2\n"
        "max_missing_rate: 0.0\n"
    )
    target = tmp_path / "expectations.yaml"
    target.write_text(content, encoding="utf-8")
    return target


def test_seed_sample_writes_dataset(tmp_path: Path, dataset_file: Path, expectations_file: Path) -> None:
    app = create_cli()
    target_root = tmp_path / "canonical"

    result = runner.invoke(
        app,
        [
            "data",
            "seed-sample",
            "--output-root",
            str(target_root),
            "--dataset",
            str(dataset_file),
            "--expectations",
            str(expectations_file),
            "--month",
            "2025-02",
            "--symbol",
            "USDJPY",
        ],
    )

    assert result.exit_code == 0, result.output
    target_file = target_root / "1h" / "USDJPY" / "2025-02" / "canonical.json"
    expect_file = target_file.with_name("dq_expectations.yaml")
    assert target_file.exists()
    assert expect_file.exists()
    loaded = json.loads(target_file.read_text(encoding="utf-8"))
    assert len(loaded) == 2

