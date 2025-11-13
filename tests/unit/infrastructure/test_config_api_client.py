from __future__ import annotations

import json

import httpx
import pytest

from infrastructure.configs.config_api_client import (
    ConfigAPIClient,
    ConfigAPIError,
    ConfigAPISettings,
)


def test_config_api_settings_requires_base_url() -> None:
    with pytest.raises(ValueError):
        ConfigAPISettings.from_mapping({})


def test_config_api_client_validate_success() -> None:
    settings = ConfigAPISettings.from_mapping(
        {
            "base_url": "https://config-api.example",
            "api_token": "secret-token",
            "timeout_seconds": 5,
            "retries": 2,
            "verify_ssl": True,
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("https://config-api.example/configs/validate")
        assert request.headers["Authorization"] == "Bearer secret-token"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["metadata"]["actor"] == "tester"
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(handler)

    client = ConfigAPIClient(
        settings,
        client_factory=lambda cfg: httpx.Client(
            base_url=cfg.base_url,
            timeout=cfg.timeout_seconds,
            verify=cfg.verify_ssl,
            transport=transport,
            headers={"Authorization": f"Bearer {cfg.api_token}"} if cfg.api_token else None,
        ),
    )

    try:
        response = client.validate({"metadata": {"actor": "tester"}})
    finally:
        client.close()

    assert response["status"] == "ok"


def test_config_api_client_raises_after_retries() -> None:
    settings = ConfigAPISettings.from_mapping(
        {"base_url": "https://config-api.example", "timeout_seconds": 1, "retries": 2, "verify_ssl": True}
    )

    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed")

    transport = httpx.MockTransport(handler)

    client = ConfigAPIClient(
        settings,
        client_factory=lambda cfg: httpx.Client(
            base_url=cfg.base_url,
            timeout=cfg.timeout_seconds,
            verify=cfg.verify_ssl,
            transport=transport,
        ),
    )

    with pytest.raises(ConfigAPIError):
        try:
            client.validate({})
        finally:
            client.close()

