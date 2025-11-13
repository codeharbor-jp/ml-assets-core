import fakeredis

from infrastructure.messaging import RedisOpsFlagRepository


def make_repository() -> RedisOpsFlagRepository:
    client = fakeredis.FakeRedis(decode_responses=True)
    return RedisOpsFlagRepository(client=client, key="core:ops:flags")


def test_repository_initializes_with_defaults() -> None:
    repository = make_repository()
    snapshot = repository.get_snapshot()
    assert snapshot.global_halt is False
    assert snapshot.leverage_scale == 1.0


def test_repository_updates_global_halt_and_persists_metadata() -> None:
    repository = make_repository()
    repository.set_global_halt(True, reason="unit-test")
    snapshot = repository.get_snapshot()
    assert snapshot.global_halt is True
    assert snapshot.metadata["reason"] == "unit-test"


def test_repository_sets_halted_pairs_and_leverage() -> None:
    repository = make_repository()
    repository.set_halted_pairs(["EURUSD", "USDJPY"], reason="halt")
    repository.set_leverage_scale(0.8, reason="risk")
    snapshot = repository.get_snapshot()
    assert "EURUSD" in snapshot.halted_pairs
    assert snapshot.leverage_scale == 0.8

