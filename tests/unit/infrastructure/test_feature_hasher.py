from __future__ import annotations

from infrastructure.features.hasher import JsonFeatureHasher


def test_json_feature_hasher_stable_for_same_payload() -> None:
    hasher = JsonFeatureHasher()
    first = hasher.compute_hash({"a": "1", "b": "2"}, {"scale": "standard"})
    second = hasher.compute_hash({"b": "2", "a": "1"}, {"scale": "standard"})
    assert first == second


def test_json_feature_hasher_changes_on_input_difference() -> None:
    hasher = JsonFeatureHasher()
    base = hasher.compute_hash({"a": "1"}, {"scale": "standard"})
    different = hasher.compute_hash({"a": "1"}, {"scale": "minmax"})
    assert base != different

