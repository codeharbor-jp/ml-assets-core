"""
Slack への通知アダプタ。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, cast

import httpx


class SlackNotificationError(RuntimeError):
    """Slack 通知が失敗した際に送出される例外。"""


@dataclass(frozen=True)
class SlackConfig:
    """
    Slack Webhook 通知に必要な設定。
    """

    webhook_url: str
    channel: str
    username: str
    timeout_seconds: float
    enabled: bool = True

    @staticmethod
    def from_mapping(mapping: Mapping[str, Any]) -> "SlackConfig":
        try:
            raw_webhook_url = mapping["webhook_url"]
        except KeyError as exc:
            raise ValueError("notifications.slack.webhook_url が設定されていません。") from exc

        if raw_webhook_url in (None, ""):
            raise ValueError("notifications.slack.webhook_url は環境設定で必須です。")

        channel = str(mapping.get("channel", "#general"))
        username = str(mapping.get("username", "ml-assets-core"))

        raw_timeout: Any = mapping.get("timeout_seconds", 5)
        try:
            timeout_seconds = float(cast(Any, raw_timeout))
        except (TypeError, ValueError) as exc:
            raise ValueError("notifications.slack.timeout_seconds は数値で指定してください。") from exc

        enabled = bool(mapping.get("enabled", True))

        if timeout_seconds <= 0:
            raise ValueError("notifications.slack.timeout_seconds は正の値で指定してください。")

        return SlackConfig(
            webhook_url=str(raw_webhook_url),
            channel=channel,
            username=username,
            timeout_seconds=timeout_seconds,
            enabled=enabled,
        )


class SlackNotifier(Protocol):
    """
    Slack への通知インターフェース。
    """

    def notify(self, message: str, *, title: str | None = None, fields: Mapping[str, str] | None = None) -> None:
        ...


class SlackWebhookNotifier(SlackNotifier):
    """
    Incoming Webhook を用いて Slack に通知する実装。
    """

    def __init__(
        self,
        config: SlackConfig,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self._config = config
        self._client = client or httpx.Client(timeout=config.timeout_seconds)

    def notify(self, message: str, *, title: str | None = None, fields: Mapping[str, str] | None = None) -> None:
        if not self._config.enabled:
            return

        payload: dict[str, object] = {
            "channel": self._config.channel,
            "username": self._config.username,
            "text": message,
        }

        if title or fields:
            attachments: list[dict[str, object]] = [
                {
                    "title": title or "Notification",
                    "fields": [{"title": key, "value": value, "short": True} for key, value in (fields or {}).items()],
                }
            ]
            payload["attachments"] = attachments

        try:
            response = self._client.post(self._config.webhook_url, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:  # pragma: no cover - ネットワーク異常パス
            raise SlackNotificationError("Slack 通知に失敗しました。") from exc

    def close(self) -> None:
        self._client.close()



