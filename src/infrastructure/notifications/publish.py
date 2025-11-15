"""
PublishUseCase の NotificationService 実装。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from application.usecases.publish import NotificationService
from .pagerduty import PagerDutyNotifier
from .slack import SlackNotifier


def _normalize(metadata: Mapping[str, str]) -> dict[str, str]:
    return {str(key): str(value) for key, value in metadata.items()}


@dataclass
class CompositePublishNotificationService(NotificationService):
    """
    Slack / PagerDuty 通知をラップした NotificationService 実装。
    """

    slack_notifier: SlackNotifier | None = None
    pagerduty_notifier: PagerDutyNotifier | None = None
    title: str = "Model Publish"

    def notify(self, status: str, message: str, metadata: Mapping[str, str]) -> None:
        fields = _normalize(metadata)
        if self.slack_notifier is not None:
            self.slack_notifier.notify(
                message=message,
                title=f"[{status.upper()}] {self.title}",
                fields=fields,
            )

        if self.pagerduty_notifier is not None:
            severity = "info" if status.lower() == "success" else "critical"
            dedup_key = fields.get("audit_record_id")
            self.pagerduty_notifier.notify(
                summary=message,
                severity=severity,
                dedup_key=dedup_key,
                custom_details=fields,
            )


@dataclass
class NoopNotificationService(NotificationService):
    """
    通知を行わないダミー実装。
    """

    def notify(self, status: str, message: str, metadata: Mapping[str, str]) -> None:  # noqa: D401
        return

