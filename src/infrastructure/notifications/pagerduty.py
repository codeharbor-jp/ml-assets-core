"""
PagerDuty への通知アダプタ。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import httpx


class PagerDutyNotificationError(RuntimeError):
    """PagerDuty への通知に失敗した場合の例外。"""


@dataclass(frozen=True)
class PagerDutyConfig:
    routing_key: str
    default_severity: str = "critical"
    source: str = "ml-assets-core"
    component: str | None = None
    group: str | None = None
    enabled: bool = True
    timeout_seconds: float = 5.0

    @staticmethod
    def from_mapping(mapping: Mapping[str, object]) -> "PagerDutyConfig":
        try:
            routing_key = str(mapping["routing_key"])
        except KeyError as exc:
            raise ValueError("notifications.pagerduty.routing_key が設定されていません。") from exc

        if not routing_key:
            raise ValueError("notifications.pagerduty.routing_key は必須です。")

        default_severity = str(mapping.get("default_severity", "critical"))
        source = str(mapping.get("source", "ml-assets-core"))
        component = mapping.get("component")
        group = mapping.get("group")
        enabled = bool(mapping.get("enabled", True))
        timeout = _to_float(mapping.get("timeout_seconds", 5.0), "notifications.pagerduty.timeout_seconds")

        return PagerDutyConfig(
            routing_key=routing_key,
            default_severity=default_severity,
            source=source,
            component=str(component) if component is not None else None,
            group=str(group) if group is not None else None,
            enabled=enabled,
            timeout_seconds=timeout,
        )


class PagerDutyNotifier:
    """
    PagerDuty Events API v2 に通知する実装。
    """

    EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"

    def __init__(self, config: PagerDutyConfig, *, client: httpx.Client | None = None) -> None:
        self._config = config
        self._client = client or httpx.Client(timeout=config.timeout_seconds)

    def notify(
        self,
        *,
        summary: str,
        severity: str | None = None,
        source: str | None = None,
        component: str | None = None,
        group: str | None = None,
        dedup_key: str | None = None,
        custom_details: Mapping[str, object] | None = None,
    ) -> None:
        if not self._config.enabled:
            return

        payload_body = {
            "summary": summary,
            "severity": (severity or self._config.default_severity),
            "source": source or self._config.source,
            "component": component or self._config.component,
            "group": group or self._config.group,
            "custom_details": dict(custom_details or {}),
        }
        payload = {
            "routing_key": self._config.routing_key,
            "event_action": "trigger",
            "dedup_key": dedup_key or "",
            "payload": payload_body,
        }

        # Remove optional fields if None to keep payload compact.
        payload["payload"] = {k: v for k, v in payload_body.items() if v is not None}
        if not payload["dedup_key"]:
            payload.pop("dedup_key")

        try:
            response = self._client.post(self.EVENTS_URL, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:  # pragma: no cover - ネットワーク異常は手動テスト想定
            raise PagerDutyNotificationError("PagerDuty への通知に失敗しました。") from exc

    def close(self) -> None:
        self._client.close()


def _to_float(value: object, field: str) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} は数値である必要があります。") from exc

