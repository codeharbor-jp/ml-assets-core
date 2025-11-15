from __future__ import annotations

import pytest

from quality import DQExpectations, ValidationError, validate_dataset


@pytest.fixture()
def expectations() -> DQExpectations:
    return DQExpectations(
        name="test-dataset",
        required_columns=("close", "volume"),
        min_rows=2,
        max_missing_rate=0.1,
        column_ranges={"close": (0.9, 1.2), "volume": (100, 2000)},
    )


def test_validate_dataset_success(expectations: DQExpectations) -> None:
    rows = [
        {"close": 1.0, "volume": 1000},
        {"close": 1.1, "volume": 1200},
    ]
    validate_dataset(rows, expectations)


def test_validate_dataset_missing_rate_violation(expectations: DQExpectations) -> None:
    rows = [
        {"close": 1.0, "volume": None},
        {"close": 1.1, "volume": None},
    ]
    with pytest.raises(ValidationError):
        validate_dataset(rows, expectations)


def test_validate_dataset_range_violation(expectations: DQExpectations) -> None:
    rows = [
        {"close": 0.5, "volume": 150},
        {"close": 1.1, "volume": 1200},
    ]
    with pytest.raises(ValidationError):
        validate_dataset(rows, expectations)
