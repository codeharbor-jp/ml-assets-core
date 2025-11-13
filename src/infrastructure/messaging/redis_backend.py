"""
Redis ベースのメッセージング実装。
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping, MutableMapping, Sequence, cast

from redis import Redis
from redis.client import PubSub

from .ops_flags import OpsFlagRepository, OpsFlagSnapshot
from .redis_channel import RedisPublisher, RedisSubscriber


@dataclass(frozen=True)
class RedisMessagingConfig:
    """
    Redis メッセージングに関する設定。
    """

    url: str
    inference_request_channel: str
    inference_signal_channel: str
    ops_event_channel: str
    ops_flag_key: str
    worker_heartbeat_key: str
    subscribe_timeout_seconds: float = 5.0
    heartbeat_ttl_seconds: int = 60

    @staticmethod
    def from_mapping(mapping: Mapping[str, object]) -> "RedisMessagingConfig":
        try:
            url = str(mapping["url"])
            channels_raw = mapping["channels"]
            keys_raw = mapping["keys"]
        except KeyError as exc:
            raise ValueError(f"redis 設定に必須キー {exc!s} が存在しません。") from exc
        channels = cast(Mapping[str, object], channels_raw)
        keys = cast(Mapping[str, object], keys_raw)

        timeouts_raw = mapping.get("timeouts")
        timeouts: Mapping[str, object] = cast(Mapping[str, object], timeouts_raw) if isinstance(timeouts_raw, Mapping) else {}

        return RedisMessagingConfig(
            url=url,
            inference_request_channel=str(channels["inference_requests"]),
            inference_signal_channel=str(channels["inference_signals"]),
            ops_event_channel=str(channels["ops_events"]),
            ops_flag_key=str(keys["ops_flags"]),
            worker_heartbeat_key=str(keys["worker_heartbeats"]),
            subscribe_timeout_seconds=float(str(timeouts.get("subscribe_timeout_seconds", 5))),
            heartbeat_ttl_seconds=int(str(timeouts.get("heartbeat_ttl_seconds", 60))),
        )


class RedisPublisherImpl(RedisPublisher):
    """
    redis-py を利用した RedisPublisher 実装。
    """

    def __init__(self, client: Redis) -> None:
        self._client = client

    def publish(self, channel: str, payload: str) -> None:
        self._client.publish(channel, payload)


class RedisSubscriberImpl(RedisSubscriber):
    """
    redis-py の Pub/Sub を利用した Subscriber 実装。
    """

    def __init__(self, client: Redis, *, timeout_seconds: float) -> None:
        self._client = client
        self._timeout_seconds = timeout_seconds
        self._subscriptions: MutableMapping[str, tuple[PubSub, threading.Thread]] = {}
        self._lock = threading.Lock()

    def subscribe(self, channel: str, callback: Callable[[str], None]) -> None:
        pubsub = self._client.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(channel)

        def listener() -> None:
            try:
                while pubsub.subscribed:
                    message = pubsub.get_message(timeout=self._timeout_seconds)
                    if message is None:
                        continue
                    if message.get("type") != "message":
                        continue
                    data = message.get("data")
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    callback(str(data))
            finally:
                pubsub.close()

        thread = threading.Thread(target=listener, name=f"RedisSubscriber-{channel}", daemon=True)
        thread.start()
        with self._lock:
            self._subscriptions[channel] = (pubsub, thread)

    def unsubscribe(self, channel: str) -> None:
        with self._lock:
            pubsub_thread = self._subscriptions.pop(channel, None)
        if not pubsub_thread:
            return
        pubsub, thread = pubsub_thread
        try:
            pubsub.unsubscribe(channel)
        finally:
            pubsub.close()
        if thread.is_alive():
            thread.join(timeout=1)


class RedisOpsFlagRepository(OpsFlagRepository):
    """
    Redis ハッシュを利用した Ops フラグリポジトリ。
    """

    def __init__(self, client: Redis, key: str) -> None:
        self._client = client
        self._key = key

    def get_snapshot(self) -> OpsFlagSnapshot:
        raw_data = cast(dict[str, object], self._client.hgetall(self._key))
        data = {str(k): str(v) for k, v in raw_data.items()}
        if not data:
            snapshot = OpsFlagSnapshot(
                global_halt=False,
                halted_pairs=[],
                flatten_pairs=[],
                leverage_scale=1.0,
                metadata=_default_metadata("initialized"),
            )
            self._store_snapshot(snapshot, reason="initialize")
            return snapshot

        def _bool(value: object) -> bool:
            return str(value).lower() in ("1", "true", "yes", "on")

        def _float(value: object) -> float:
            return float(str(value))

        halted_pairs = _loads_sequence(data.get("halted_pairs", "[]"))
        flatten_pairs = _loads_sequence(data.get("flatten_pairs", "[]"))
        metadata = _loads_mapping(data.get("metadata", "{}"))

        return OpsFlagSnapshot(
            global_halt=_bool(data.get("global_halt", "false")),
            halted_pairs=halted_pairs,
            flatten_pairs=flatten_pairs,
            leverage_scale=_float(data.get("leverage_scale", 1.0)),
            metadata=metadata,
        )

    def set_global_halt(self, value: bool, *, reason: str) -> None:
        self._client.hset(
            self._key,
            mapping={
                "global_halt": "1" if value else "0",
                "metadata": _metadata_json(reason, {"global_halt": str(value)}),
            },
        )

    def set_halted_pairs(self, pairs: Sequence[str], *, reason: str) -> None:
        self._client.hset(
            self._key,
            mapping={
                "halted_pairs": json.dumps(sorted(set(pairs))),
                "metadata": _metadata_json(reason, {"halted_pairs": ",".join(sorted(set(pairs)))}),
            },
        )

    def set_flatten_pairs(self, pairs: Sequence[str], *, reason: str) -> None:
        self._client.hset(
            self._key,
            mapping={
                "flatten_pairs": json.dumps(sorted(set(pairs))),
                "metadata": _metadata_json(reason, {"flatten_pairs": ",".join(sorted(set(pairs)))}),
            },
        )

    def set_leverage_scale(self, value: float, *, reason: str) -> None:
        if value <= 0:
            raise ValueError("leverage_scale は正の値である必要があります。")
        self._client.hset(
            self._key,
            mapping={
                "leverage_scale": f"{value:.6f}",
                "metadata": _metadata_json(reason, {"leverage_scale": f"{value:.6f}"}),
            },
        )

    def _store_snapshot(self, snapshot: OpsFlagSnapshot, *, reason: str) -> None:
        self._client.hset(
            self._key,
            mapping={
                "global_halt": "1" if snapshot.global_halt else "0",
                "halted_pairs": json.dumps(list(snapshot.halted_pairs)),
                "flatten_pairs": json.dumps(list(snapshot.flatten_pairs)),
                "leverage_scale": f"{snapshot.leverage_scale:.6f}",
                "metadata": _metadata_json(reason, snapshot.metadata),
            },
        )


def _loads_sequence(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, bytes):
        text = value.decode("utf-8")
    else:
        text = str(value)
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(loaded, Sequence):
        return []
    return [str(item) for item in loaded]


def _loads_mapping(value: object) -> Mapping[str, str]:
    if value is None:
        return {}
    if isinstance(value, bytes):
        text = value.decode("utf-8")
    else:
        text = str(value)
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(loaded, Mapping):
        return {}
    return {str(k): str(v) for k, v in loaded.items()}


def _metadata_json(reason: str, extra: Mapping[str, str]) -> str:
    metadata = dict(_default_metadata(reason))
    metadata.update({str(k): str(v) for k, v in extra.items()})
    return json.dumps(metadata)


def _default_metadata(reason: str) -> Mapping[str, str]:
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "source": "ml-assets-core",
    }


def write_heartbeat(client: Redis, key: str, worker_id: str, ttl_seconds: int) -> None:
    """
    ワーカーのハートビートを Redis に記録するユーティリティ。
    """

    client.setex(name=f"{key}:{worker_id}", time=ttl_seconds, value=str(time.time()))

