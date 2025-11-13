import json
from datetime import datetime, timedelta, timezone
from typing import Sequence

import fakeredis

from application.usecases import InferenceRequest, InferenceResponse, InferenceUseCase
from domain.models.signal import Signal, SignalLeg, TradeSide
from infrastructure.messaging import OpsFlagRepository, OpsFlagSnapshot, RedisMessagingConfig, RedisPublisher, RedisSubscriber
from interfaces.workers import InferenceWorker, InferenceWorkerConfig


class DummyInferenceUseCase(InferenceUseCase):
    def __init__(self) -> None:
        self.calls: list[InferenceRequest] = []

    def execute(self, request: InferenceRequest) -> InferenceResponse:
        self.calls.append(request)
        signal = Signal(
            signal_id="sig-1",
            timestamp=datetime.now(timezone.utc),
            pair_id="EURUSD",
            legs=[SignalLeg(symbol="EURUSD", side=TradeSide.LONG, beta_weight=1.0, notional=1000.0)],
            return_prob=0.75,
            risk_score=0.2,
            theta1=0.7,
            theta2=0.3,
            position_scale=1.0,
            model_version="model-1",
            valid_until=datetime.now(timezone.utc) + timedelta(minutes=1),
            metadata={},
        )
        return InferenceResponse(signals=[signal], diagnostics={"latency_ms": 10})


class AlwaysAllowOpsRepository(OpsFlagRepository):
    def get_snapshot(self) -> OpsFlagSnapshot:
        return OpsFlagSnapshot(
            global_halt=False,
            halted_pairs=[],
            flatten_pairs=[],
            leverage_scale=1.0,
            metadata={},
        )

    def set_global_halt(self, value: bool, *, reason: str) -> None:  # pragma: no cover - not used in this test
        raise NotImplementedError

    def set_halted_pairs(self, pairs: Sequence[str], *, reason: str) -> None:  # pragma: no cover - not used
        raise NotImplementedError

    def set_flatten_pairs(self, pairs: Sequence[str], *, reason: str) -> None:  # pragma: no cover - not used
        raise NotImplementedError

    def set_leverage_scale(self, value: float, *, reason: str) -> None:  # pragma: no cover - not used
        raise NotImplementedError


class HaltOpsRepository(AlwaysAllowOpsRepository):
    def get_snapshot(self) -> OpsFlagSnapshot:
        return OpsFlagSnapshot(
            global_halt=True,
            halted_pairs=[],
            flatten_pairs=[],
            leverage_scale=1.0,
            metadata={},
        )


class DummyPublisher(RedisPublisher):
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def publish(self, channel: str, payload: str) -> None:
        self.messages.append((channel, payload))


class DummySubscriber(RedisSubscriber):
    def __init__(self) -> None:
        self._callback = None
        self.subscribed_channel: str | None = None

    def subscribe(self, channel: str, callback) -> None:
        self._callback = callback
        self.subscribed_channel = channel

    def unsubscribe(self, channel: str) -> None:
        self._callback = None
        self.subscribed_channel = None

    def trigger(self, payload: str) -> None:
        if self._callback:
            self._callback(payload)


def make_worker(ops_repository: OpsFlagRepository | None = None) -> tuple[InferenceWorker, DummyPublisher, DummySubscriber, DummyInferenceUseCase]:
    messaging_config = RedisMessagingConfig.from_mapping(
        {
            "url": "redis://localhost:6379/0",
            "channels": {
                "inference_requests": "core:inference:requests",
                "inference_signals": "core:inference:signals",
                "ops_events": "core:ops:events",
            },
            "keys": {
                "ops_flags": "core:ops:flags",
                "worker_heartbeats": "core:workers:heartbeats",
            },
            "timeouts": {
                "subscribe_timeout_seconds": 1,
                "heartbeat_ttl_seconds": 10,
            },
        }
    )
    config = InferenceWorkerConfig(worker_id="worker-1", poll_interval_seconds=0.01, heartbeat_interval_seconds=1.0)
    inference_usecase = DummyInferenceUseCase()
    publisher = DummyPublisher()
    subscriber = DummySubscriber()
    redis_client = fakeredis.FakeRedis()
    worker = InferenceWorker(
        config=config,
        messaging_config=messaging_config,
        inference_usecase=inference_usecase,
        request_subscriber=subscriber,
        signal_publisher=publisher,
        ops_repository=ops_repository or AlwaysAllowOpsRepository(),
        redis_client=redis_client,
        clock=lambda: 0.0,
    )
    return worker, publisher, subscriber, inference_usecase


def make_payload(partitions: Sequence[str]) -> str:
    request = {
        "partition_ids": partitions,
        "theta_params": {
            "theta1": 0.7,
            "theta2": 0.3,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": "tester",
            "source_model_version": "model-1",
        },
        "metadata": {"request_id": "req-1"},
    }
    return json.dumps(request)


def test_worker_publishes_signals_on_message() -> None:
    worker, publisher, subscriber, inference_usecase = make_worker()
    payload = make_payload(["EURUSD"])
    worker.handle_message(payload)

    assert inference_usecase.calls, "inference usecase should be invoked"
    assert publisher.messages, "signals should be published"
    channel, message = publisher.messages[0]
    assert channel == "core:inference:signals"
    assert "signals" in message


def test_worker_skips_when_global_halt() -> None:
    worker, publisher, _, inference_usecase = make_worker(ops_repository=HaltOpsRepository())
    payload = make_payload(["EURUSD"])
    worker.handle_message(payload)

    assert not publisher.messages
    assert not inference_usecase.calls

