"""
Redis Pub/Sub チャネルインターフェース。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol


class RedisPublisher(Protocol):
    """Redis へメッセージを publish するためのインターフェース。"""

    def publish(self, channel: str, payload: str) -> None:
        ...


class RedisSubscriber(Protocol):
    """Redis のメッセージを購読するためのインターフェース。"""

    def subscribe(self, channel: str, callback: Callable[[str], None]) -> None:
        ...

    def unsubscribe(self, channel: str) -> None:
        ...


@dataclass(frozen=True)
class RedisChannel:
    """
    Publish/Subscribe をまとめたチャネル表現。

    Attributes:
        name: チャネル名。
        publisher: RedisPublisher の実装。
        subscriber: RedisSubscriber の実装。
    """

    name: str
    publisher: RedisPublisher
    subscriber: RedisSubscriber

    def publish(self, payload: str) -> None:
        self.publisher.publish(self.name, payload)

    def subscribe(self, callback: Callable[[str], None]) -> None:
        self.subscriber.subscribe(self.name, callback)

    def unsubscribe(self) -> None:
        self.subscriber.unsubscribe(self.name)

