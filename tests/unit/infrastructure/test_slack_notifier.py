from __future__ import annotations

import json

import httpx
import pytest

from infrastructure.notifications.slack import SlackConfig, SlackNotificationError, SlackWebhookNotifier


def test_slack_config_requires_webhook() -> None:
    with pytest.raises(ValueError):
        SlackConfig.from_mapping({})


def test_slack_notifier_sends_payload() -> None:
    config = SlackConfig.from_mapping(
        {
            "webhook_url": "https://hooks.slack.com/services/T000/B000/XXXX",
            "channel": "#alerts",
            "username": "bot",
            "timeout_seconds": 3,
        }
    )

    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200)

    notifier = SlackWebhookNotifier(
        config,
        client=httpx.Client(timeout=3, transport=httpx.MockTransport(handler)),
    )

    notifier.notify("System resumed", title="ops.resume", fields={"global_halt": "false"})

    assert captured["url"] == config.webhook_url
    payload = captured["payload"]
    assert payload["channel"] == "#alerts"
    assert payload["text"] == "System resumed"
    assert payload["attachments"][0]["title"] == "ops.resume"
    assert payload["attachments"][0]["fields"][0]["title"] == "global_halt"


def test_slack_notifier_disabled_does_not_send() -> None:
    config = SlackConfig.from_mapping(
        {
            "webhook_url": "https://hooks.slack.com/services/T/B/C",
            "enabled": False,
        }
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(200))
    notifier = SlackWebhookNotifier(config, client=httpx.Client(timeout=3, transport=transport))
    notifier.notify("message")

    # transport should not be invoked when disabled
    notifier.close()


def test_slack_notifier_raises_on_error() -> None:
    config = SlackConfig.from_mapping({"webhook_url": "https://hooks.slack.com/services/T/B/C"})

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    notifier = SlackWebhookNotifier(config, client=httpx.Client(timeout=3, transport=httpx.MockTransport(handler)))

    with pytest.raises(SlackNotificationError):
        notifier.notify("failure")

    notifier.close()

