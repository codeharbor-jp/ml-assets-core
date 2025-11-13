import json
from datetime import datetime, timezone
from typing import Iterable, Mapping, Sequence

from application.services.feature_builder import (
    DataQualityThresholdExceededError,
    FeatureBuilder,
    FeatureBuilderConfig,
    FeatureBuildRequest,
    FeatureCache,
    FeatureGenerator,
    FeatureHasher,
    FeatureVector,
    QuarantinedPartitionError,
)
from domain import DataQualitySnapshot, DatasetPartition


class DummyCache(FeatureCache):
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], tuple[FeatureVector, ...]] = {}
        self.invalidations: list[str] = []

    def _key(self, partition: DatasetPartition, feature_hash: str) -> tuple[str, str]:
        identifier = f"{partition.timeframe}:{partition.symbol}:{partition.year:04d}{partition.month:02d}"
        return identifier, feature_hash

    def exists(self, *, partition: DatasetPartition, feature_hash: str) -> bool:
        return self._key(partition, feature_hash) in self._store

    def load(self, *, partition: DatasetPartition, feature_hash: str) -> Iterable[FeatureVector]:
        key = self._key(partition, feature_hash)
        return list(self._store[key])

    def store(
        self,
        *,
        partition: DatasetPartition,
        feature_hash: str,
        features: Iterable[FeatureVector],
        schema_hash: str,
    ) -> None:
        key = self._key(partition, feature_hash)
        self._store[key] = tuple(features)

    def invalidate(self, *, partition: DatasetPartition, reason: str) -> None:
        self.invalidations.append(reason)
        key_prefix = f"{partition.timeframe}:{partition.symbol}:{partition.year:04d}{partition.month:02d}"
        to_remove = [key for key in self._store if key[0] == key_prefix]
        for key in to_remove:
            self._store.pop(key, None)


class DummyHasher(FeatureHasher):
    def compute_hash(self, feature_spec: Mapping[str, str], preprocessing: Mapping[str, str]) -> str:
        payload = {"spec": dict(feature_spec), "preprocessing": dict(preprocessing)}
        return json.dumps(payload, sort_keys=True)


class DummyGenerator(FeatureGenerator):
    def __init__(self, features: Sequence[FeatureVector]) -> None:
        self._features = tuple(features)
        self.calls = 0

    def generate(
        self,
        *,
        partition: DatasetPartition,
        feature_spec: Mapping[str, str],
        preprocessing: Mapping[str, str],
    ) -> Iterable[FeatureVector]:
        self.calls += 1
        return list(self._features)


def make_partition(symbol: str = "EURUSD") -> DatasetPartition:
    return DatasetPartition(
        timeframe="1h",
        symbol=symbol,
        year=2024,
        month=1,
        last_timestamp=datetime(2024, 1, 31, 23, tzinfo=timezone.utc),
        bars_written=100,
        missing_gaps=2,
        outlier_bars=1,
        spike_flags=1,
        quarantine_flag=False,
        data_hash="hash123",
    )


def make_snapshot(
    *,
    bars_written: int = 100,
    missing: int = 2,
    outliers: int = 1,
    spikes: int = 1,
    quarantined: bool = False,
) -> DataQualitySnapshot:
    return DataQualitySnapshot(
        bars_written=bars_written,
        missing_gaps=missing,
        outlier_bars=outliers,
        spike_flags=spikes,
        quarantined=quarantined,
    )


def make_request(
    *,
    force_rebuild: bool = False,
    snapshot: DataQualitySnapshot | None = None,
) -> FeatureBuildRequest:
    partition = make_partition()
    return FeatureBuildRequest(
        partition=partition,
        feature_spec={"name": "basic_features"},
        preprocessing={"version": "1"},
        dq_snapshot=snapshot or make_snapshot(),
        force_rebuild=force_rebuild,
    )


def make_builder(
    *,
    cache: DummyCache | None = None,
    generator: DummyGenerator | None = None,
    config: FeatureBuilderConfig | None = None,
) -> tuple[FeatureBuilder, DummyCache, DummyGenerator]:
    cache = cache or DummyCache()
    generator = generator or DummyGenerator([{"feature_a": 1.0}])
    config = config or FeatureBuilderConfig(missing_threshold=0.1, outlier_threshold=0.2, spike_threshold=0.2)
    builder = FeatureBuilder(cache, generator, DummyHasher(), config)
    return builder, cache, generator


def test_feature_builder_generates_and_caches_features() -> None:
    builder, cache, generator = make_builder()
    request = make_request()

    result = builder.build(request)

    assert generator.calls == 1
    assert result.metadata["cached"] == "false"
    assert cache.exists(partition=request.partition, feature_hash=result.feature_hash)


def test_feature_builder_uses_cache_on_subsequent_calls() -> None:
    builder, cache, generator = make_builder()
    request = make_request()
    first = builder.build(request)
    second = builder.build(request)

    assert generator.calls == 1
    assert first.feature_hash == second.feature_hash
    assert second.metadata["cached"] == "true"


def test_feature_builder_force_rebuild_invalidates_cache() -> None:
    cache = DummyCache()
    hasher = DummyHasher()
    config = FeatureBuilderConfig(missing_threshold=0.1, outlier_threshold=0.2, spike_threshold=0.2)

    initial_builder = FeatureBuilder(cache, DummyGenerator([{"feature_a": 1.0}]), hasher, config)
    request = make_request()
    initial_builder.build(request)

    updated_generator = DummyGenerator([{"feature_a": 2.0}])
    builder = FeatureBuilder(cache, updated_generator, hasher, config)
    rebuilt = builder.build(make_request(force_rebuild=True))

    assert updated_generator.calls == 1
    assert rebuilt.metadata["cached"] == "false"
    assert "force_rebuild" in cache.invalidations
    assert rebuilt.features[0]["feature_a"] == 2.0


def test_feature_builder_raises_on_quarantine() -> None:
    builder, cache, _ = make_builder()
    request = make_request(snapshot=make_snapshot(quarantined=True))

    try:
        builder.build(request)
        assert False, "QuarantinedPartitionError was not raised"
    except QuarantinedPartitionError:
        assert "partition_quarantined" in cache.invalidations


def test_feature_builder_raises_when_quality_threshold_exceeded() -> None:
    builder, cache, _ = make_builder()
    snapshot = make_snapshot(missing=20)  # 20% missing > 10% threshold

    try:
        builder.build(make_request(snapshot=snapshot))
        assert False, "DataQualityThresholdExceededError was not raised"
    except DataQualityThresholdExceededError as exc:
        assert exc.flag.name == "MISSING"
        assert "dq_flag_missing" in cache.invalidations


def test_feature_builder_respects_warning_configuration() -> None:
    config = FeatureBuilderConfig(missing_threshold=0.3, outlier_threshold=0.3, spike_threshold=0.01, allow_warning=False)
    builder, cache, _ = make_builder(config=config)
    snapshot = make_snapshot(spikes=5)  # 5% spike rate exceeds 1%

    try:
        builder.build(make_request(snapshot=snapshot))
        assert False, "DataQualityThresholdExceededError was not raised"
    except DataQualityThresholdExceededError:
        assert "dq_flag_warning" in cache.invalidations

