from __future__ import annotations

import json
from collections import deque
from typing import Any

import httpx

from infrastructure.notifications.pagerduty import PagerDutyConfig, PagerDutyNotifier


class _RecordingTransport(httpx.BaseTransport):
    def __init__(self) -> None:
        self.requests: deque[httpx.Request] = deque()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(202, json={"status": "success"})


def test_pagerduty_notifier_sends_payload() -> None:
    transport = _RecordingTransport()
    client = httpx.Client(transport=transport)
    config = PagerDutyConfig(
        routing_key="test-key",
        default_severity="warning",
        source="ml-assets-core",
        component="inference",
    )

    notifier = PagerDutyNotifier(config, client=client)
    notifier.notify(
        summary="Inference latency breach",
        severity="critical",
        dedup_key="inference-123",
        custom_details={"latency_ms": 250},
    )

    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.method == "POST"
    payload: dict[str, Any] = json.loads(request.content)
    assert payload["routing_key"] == "test-key"
    assert payload["event_action"] == "trigger"
    assert payload["payload"]["severity"] == "critical"
    assert payload["payload"]["custom_details"]["latency_ms"] == 250

    notifier.close()


def test_pagerduty_notifier_disabled() -> None:
    transport = _RecordingTransport()
    client = httpx.Client(transport=transport)
    config = PagerDutyConfig(
        routing_key="test-key",
        enabled=False,
    )

    notifier = PagerDutyNotifier(config, client=client)
    notifier.notify(summary="Ignored event")
    assert len(transport.requests) == 0
    notifier.close()

