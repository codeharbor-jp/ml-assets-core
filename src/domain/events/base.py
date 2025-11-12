"""
ドメインイベントの基底定義。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Type, TypeVar
from uuid import uuid4

TEvent = TypeVar("TEvent", bound="DomainEvent")


@dataclass(frozen=True)
class DomainEvent:
    """
    ドメインイベントの基底クラス。

    Attributes:
        event_id: 一意のイベントID。
        occurred_at: 発生日時（UTC）。
        source: 発生元コンポーネント。
    """

    event_id: str
    occurred_at: datetime
    source: str

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("event_id は必須です。")
        if not self.source:
            raise ValueError("source は必須です。")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at はタイムゾーン情報付きの datetime を指定してください。")

    @classmethod
    def create(cls: Type[TEvent], *, source: str, occurred_at: datetime | None = None, **kwargs) -> TEvent:
        """
        サブクラスの構築を補助するファクトリメソッド。
        """

        occurred = occurred_at or datetime.now(timezone.utc)
        return cls(event_id=str(uuid4()), occurred_at=occurred, source=source, **kwargs)

