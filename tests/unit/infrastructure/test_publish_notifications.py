from __future__ import annotations

from typing import Mapping
from unittest.mock import MagicMock

import pytest

from infrastructure.notifications import CompositePublishNotificationService, NoopNotificationService


@pytest.fixture(name="metadata")
def _metadata() -> Mapping[str, str]:
    return {"model_version": "v1", "audit_record_id": "audit-001"}


def test_composite_service_notifies_all_channels(metadata: Mapping[str, str]) -> None:
    slack = MagicMock()
    pagerduty = MagicMock()

    service = CompositePublishNotificationService(slack_notifier=slack, pagerduty_notifier=pagerduty)

    service.notify("success", "model deployed", metadata)

    slack.notify.assert_called_once()
    args, kwargs = slack.notify.call_args
    assert kwargs["title"].startswith("[SUCCESS]")

    pagerduty.notify.assert_called_once()
    pd_kwargs = pagerduty.notify.call_args.kwargs
    assert pd_kwargs["severity"] == "info"
    assert pd_kwargs["custom_details"]["model_version"] == "v1"


def test_composite_service_sets_critical_on_failure(metadata: Mapping[str, str]) -> None:
    pagerduty = MagicMock()
    service = CompositePublishNotificationService(slack_notifier=None, pagerduty_notifier=pagerduty)

    service.notify("error", "registry update failed", metadata)

    pagerduty.notify.assert_called_once()
    pd_kwargs = pagerduty.notify.call_args.kwargs
    assert pd_kwargs["severity"] == "critical"


def test_noop_notification_service(metadata: Mapping[str, str]) -> None:
    service = NoopNotificationService()
    service.notify("success", "noop", metadata)

