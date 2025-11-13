"""
推論ワーカープロセス。
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Mapping, Sequence

from application.usecases import InferenceRequest, InferenceUseCase
from domain import Signal, ThetaParams
from domain.models.signal import SignalLeg
from infrastructure.messaging import (
    OpsFlagRepository,
    RedisMessagingConfig,
    RedisPublisher,
    RedisSubscriber,
    write_heartbeat,
)
from redis import Redis


LOGGER = logging.getLogger("ml_assets_core.inference.worker")


@dataclass(frozen=True)
class InferenceWorkerConfig:
    """
    推論ワーカーの設定。
    """

    worker_id: str
    poll_interval_seconds: float = 0.1
    heartbeat_interval_seconds: float = 30.0


class InferenceWorker:
    """
    Redis チャネルを介して推論リクエストを受け取り、シグナルを配信するワーカー。
    """

    def __init__(
        self,
        *,
        config: InferenceWorkerConfig,
        messaging_config: RedisMessagingConfig,
        inference_usecase: InferenceUseCase,
        request_subscriber: RedisSubscriber,
        signal_publisher: RedisPublisher,
        ops_repository: OpsFlagRepository,
        redis_client: Redis,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._config = config
        self._messaging_config = messaging_config
        self._inference_usecase = inference_usecase
        self._request_subscriber = request_subscriber
        self._signal_publisher = signal_publisher
        self._ops_repository = ops_repository
        self._redis_client = redis_client
        self._clock = clock or time.monotonic
        self._last_heartbeat = 0.0
        self._running = threading.Event()

    def start(self) -> None:
        """
        ワーカーを起動し、Redis チャネルへの購読を開始する。
        """

        LOGGER.info("Starting inference worker '%s'", self._config.worker_id)
        self._running.set()
        self._request_subscriber.subscribe(self._messaging_config.inference_request_channel, self.handle_message)

        while self._running.is_set():
            now = self._clock()
            if now - self._last_heartbeat >= self._config.heartbeat_interval_seconds:
                write_heartbeat(
                    self._redis_client,
                    self._messaging_config.worker_heartbeat_key,
                    self._config.worker_id,
                    self._messaging_config.heartbeat_ttl_seconds,
                )
                self._last_heartbeat = now
            time.sleep(self._config.poll_interval_seconds)

    def stop(self) -> None:
        """
        ワーカーを停止し、購読を解除する。
        """

        LOGGER.info("Stopping inference worker '%s'", self._config.worker_id)
        self._running.clear()
        self._request_subscriber.unsubscribe(self._messaging_config.inference_request_channel)

    def handle_message(self, payload: str) -> None:
        """
        受信した推論リクエストを処理する。
        """

        LOGGER.debug("Received inference payload: %s", payload)
        try:
            request = _decode_inference_request(payload)
        except ValueError as exc:
            LOGGER.error("Failed to decode inference request: %s", exc)
            return

        snapshot = self._ops_repository.get_snapshot()
        if snapshot.global_halt:
            LOGGER.warning("Global halt active. Skipping inference for %s", request.partition_ids)
            return

        start = self._clock()
        response = self._inference_usecase.execute(request)
        duration_ms = (self._clock() - start) * 1000.0

        LOGGER.info(
            "Inference completed. partitions=%s signals=%d duration_ms=%.2f",
            ",".join(request.partition_ids),
            len(response.signals),
            duration_ms,
        )

        diagnostics: dict[str, object] = dict(response.diagnostics)
        diagnostics.update(
            {
                "inference_duration_ms": f"{duration_ms:.2f}",
                "worker_id": self._config.worker_id,
            }
        )

        payload_dict = {
            "signals": [_serialize_signal(signal) for signal in response.signals],
            "metadata": request.metadata,
            "diagnostics": diagnostics,
        }
        self._signal_publisher.publish(
            self._messaging_config.inference_signal_channel,
            json.dumps(payload_dict),
        )


def _deserialize_theta_params(data: Mapping[str, object]) -> ThetaParams:
    try:
        updated_at = datetime.fromisoformat(str(data["updated_at"]))
        return ThetaParams(
            theta1=float(str(data["theta1"])),
            theta2=float(str(data["theta2"])),
            updated_at=updated_at,
            updated_by=str(data["updated_by"]),
            source_model_version=str(data.get("source_model_version"))
            if data.get("source_model_version") is not None
            else None,
        )
    except KeyError as exc:
        raise ValueError(f"theta_params に必須キー {exc!s} が存在しません。") from exc


def _decode_inference_request(payload: str) -> InferenceRequest:
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON デコードに失敗しました: {exc}") from exc

    if not isinstance(raw, Mapping):
        raise ValueError("推論リクエストの形式が不正です。")

    partitions = raw.get("partition_ids")
    if not isinstance(partitions, Sequence):
        raise ValueError("partition_ids は配列である必要があります。")

    theta_params_raw = raw.get("theta_params")
    if not isinstance(theta_params_raw, Mapping):
        raise ValueError("theta_params が存在しません。")

    metadata = raw.get("metadata") or {}
    if not isinstance(metadata, Mapping):
        raise ValueError("metadata は Mapping である必要があります。")

    return InferenceRequest(
        partition_ids=[str(partition) for partition in partitions],
        theta_params=_deserialize_theta_params(theta_params_raw),
        metadata={str(k): str(v) for k, v in metadata.items()},
    )


def _serialize_signal(signal: Signal) -> Mapping[str, object]:
    return {
        "signal_id": signal.signal_id,
        "timestamp": signal.timestamp.isoformat(),
        "pair_id": signal.pair_id,
        "legs": [_serialize_leg(leg) for leg in signal.legs],
        "return_prob": signal.return_prob,
        "risk_score": signal.risk_score,
        "theta1": signal.theta1,
        "theta2": signal.theta2,
        "position_scale": signal.position_scale,
        "model_version": signal.model_version,
        "valid_until": signal.valid_until.isoformat(),
        "metadata": dict(signal.metadata),
    }


def _serialize_leg(leg: SignalLeg) -> Mapping[str, object]:
    return {
        "symbol": leg.symbol,
        "side": leg.side.value,
        "beta_weight": leg.beta_weight,
        "notional": leg.notional,
    }

