from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Sequence

from application.usecases.ops import OpsCommand, OpsService, OpsResponse, OpsAuditLogger
from infrastructure.messaging import OpsFlagRepository, OpsFlagSnapshot, RedisPublisher


@dataclass
class InMemoryOpsFlagRepository(OpsFlagRepository):
    snapshot: OpsFlagSnapshot = field(
        default_factory=lambda: OpsFlagSnapshot(
            global_halt=False,
            halted_pairs=[],
            flatten_pairs=[],
            leverage_scale=1.0,
            metadata={},
        )
    )

    def get_snapshot(self) -> OpsFlagSnapshot:
        return self.snapshot

    def set_global_halt(self, value: bool, *, reason: str) -> None:
        self.snapshot = OpsFlagSnapshot(
            global_halt=value,
            halted_pairs=self.snapshot.halted_pairs,
            flatten_pairs=self.snapshot.flatten_pairs,
            leverage_scale=self.snapshot.leverage_scale,
            metadata={"reason": reason},
        )

    def set_halted_pairs(self, pairs: Sequence[str], *, reason: str) -> None:
        self.snapshot = OpsFlagSnapshot(
            global_halt=self.snapshot.global_halt,
            halted_pairs=list(pairs),
            flatten_pairs=self.snapshot.flatten_pairs,
            leverage_scale=self.snapshot.leverage_scale,
            metadata={"reason": reason},
        )

    def set_flatten_pairs(self, pairs: Sequence[str], *, reason: str) -> None:
        self.snapshot = OpsFlagSnapshot(
            global_halt=self.snapshot.global_halt,
            halted_pairs=self.snapshot.halted_pairs,
            flatten_pairs=list(pairs),
            leverage_scale=self.snapshot.leverage_scale,
            metadata={"reason": reason},
        )

    def set_leverage_scale(self, value: float, *, reason: str) -> None:
        self.snapshot = OpsFlagSnapshot(
            global_halt=self.snapshot.global_halt,
            halted_pairs=self.snapshot.halted_pairs,
            flatten_pairs=self.snapshot.flatten_pairs,
            leverage_scale=value,
            metadata={"reason": reason},
        )


class DummyAuditLogger(OpsAuditLogger):
    def __init__(self) -> None:
        self.events: list[tuple[str, Mapping[str, str]]] = []

    def log(self, event_name: str, payload: Mapping[str, str]) -> None:
        self.events.append((event_name, dict(payload)))


class DummyPublisher(RedisPublisher):
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    def publish(self, channel: str, payload: str) -> None:
        self.published.append((channel, payload))


class DummyNotifier:
    def __init__(self) -> None:
        self.notifications: list[tuple[str | None, str, Mapping[str, str]]] = []

    def notify(self, message: str, *, title: str | None = None, fields: Mapping[str, str] | None = None) -> None:
        self.notifications.append((title, message, dict(fields or {})))


def make_service(
    repo: InMemoryOpsFlagRepository | None = None,
) -> tuple[OpsService, InMemoryOpsFlagRepository, DummyAuditLogger, DummyPublisher, DummyNotifier]:
    repository = repo or InMemoryOpsFlagRepository()
    audit = DummyAuditLogger()
    publisher = DummyPublisher()
    notifier = DummyNotifier()
    service = OpsService(
        repository=repository,
        audit_logger=audit,
        event_publisher=publisher,
        ops_event_channel="core:ops:events",
        notifier=notifier,
    )
    return service, repository, audit, publisher, notifier


def test_status_returns_snapshot_details() -> None:
    service, _, audit, _, notifier = make_service()
    response = service.execute(OpsCommand(command="status", arguments={}))
    assert response.status == "ok"
    assert "global_halt" in response.details
    assert audit.events[0][0] == "ops.status"
    assert notifier.notifications, "status command should trigger notifier when enabled"


def test_halt_global_updates_repository_and_publishes() -> None:
    service, repository, audit, publisher, notifier = make_service()
    response = service.execute(
        OpsCommand(
            command="halt_global",
            arguments={},
            metadata={"actor": "unit-test"},
        )
    )
    assert repository.get_snapshot().global_halt is True
    assert response.status == "ok"
    assert audit.events[0][0] == "ops.halt_global"
    assert publisher.published, "ops events should be published"
    assert notifier.notifications[-1][0] == "ops.halt_global"


def test_unsupported_command_returns_error() -> None:
    service, _, _, _, notifier = make_service()
    response = service.execute(OpsCommand(command="unknown", arguments={}))
    assert response.status == "error"
    assert isinstance(response, OpsResponse)
    assert not notifier.notifications

