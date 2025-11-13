from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Mapping, Sequence

import httpx

from application.usecases.configs import ConfigManagementService, ConfigPRRequest, ConfigValidationRequest
from application.usecases.ops import OpsAuditLogger, OpsCommand, OpsService
from infrastructure.configs.config_api_client import ConfigAPIClient, ConfigAPISettings
from infrastructure.databases.postgres import PostgresConfig
from infrastructure.messaging import OpsFlagRepository, OpsFlagSnapshot
from infrastructure.notifications.slack import SlackConfig, SlackWebhookNotifier


@dataclass
class InMemoryOpsFlagRepository(OpsFlagRepository):
    snapshot: OpsFlagSnapshot = field(
        default_factory=lambda: OpsFlagSnapshot(
            global_halt=False,
            halted_pairs=[],
            flatten_pairs=[],
            leverage_scale=1.0,
            metadata={},
        )
    )

    def get_snapshot(self) -> OpsFlagSnapshot:
        return self.snapshot

    def set_global_halt(self, value: bool, *, reason: str) -> None:
        self.snapshot = OpsFlagSnapshot(
            global_halt=value,
            halted_pairs=self.snapshot.halted_pairs,
            flatten_pairs=self.snapshot.flatten_pairs,
            leverage_scale=self.snapshot.leverage_scale,
            metadata={"reason": reason},
        )

    def set_halted_pairs(self, pairs: Sequence[str], *, reason: str) -> None:  # pragma: no cover - not used here
        self.snapshot = OpsFlagSnapshot(
            global_halt=self.snapshot.global_halt,
            halted_pairs=list(pairs),
            flatten_pairs=self.snapshot.flatten_pairs,
            leverage_scale=self.snapshot.leverage_scale,
            metadata={"reason": reason},
        )

    def set_flatten_pairs(self, pairs: Sequence[str], *, reason: str) -> None:  # pragma: no cover - not used here
        self.snapshot = OpsFlagSnapshot(
            global_halt=self.snapshot.global_halt,
            halted_pairs=self.snapshot.halted_pairs,
            flatten_pairs=list(pairs),
            leverage_scale=self.snapshot.leverage_scale,
            metadata={"reason": reason},
        )

    def set_leverage_scale(self, value: float, *, reason: str) -> None:  # pragma: no cover - not used here
        self.snapshot = OpsFlagSnapshot(
            global_halt=self.snapshot.global_halt,
            halted_pairs=self.snapshot.halted_pairs,
            flatten_pairs=self.snapshot.flatten_pairs,
            leverage_scale=value,
            metadata={"reason": reason},
        )


class DummyAuditLogger(OpsAuditLogger):
    def __init__(self) -> None:
        self.events: list[tuple[str, Mapping[str, str]]] = []

    def log(self, event_name: str, payload: Mapping[str, str]) -> None:
        self.events.append((event_name, dict(payload)))


def _build_httpx_client(settings: ConfigAPISettings, handler: httpx.MockTransport) -> httpx.Client:
    headers = {"Authorization": f"Bearer {settings.api_token}"} if settings.api_token else None
    return httpx.Client(
        base_url=settings.base_url,
        timeout=settings.timeout_seconds,
        verify=settings.verify_ssl,
        transport=handler,
        headers=headers,
    )


def test_external_integrations_roundtrip() -> None:
    # Postgres 設定のパース確認
    pg_mapping = {
        "dsn": "postgresql://mlcore:secret@localhost:5432/ml_assets_core",
        "pool": {"min_size": 1, "max_size": 5, "timeout_seconds": 5},
        "statement_timeout_ms": 20000,
        "search_path": ["core", "audit", "public"],
        "schemas": {"core": "core", "audit": "audit"},
    }
    pg_config = PostgresConfig.from_mapping(pg_mapping)
    assert pg_config.pool.max_size == 5

    # Config API クライアントをモックで検証
    config_settings = ConfigAPISettings.from_mapping(
        {
            "base_url": "https://config-api.example",
            "api_token": "token",
            "timeout_seconds": 3,
            "retries": 2,
            "verify_ssl": True,
        }
    )

    config_requests: list[dict[str, object]] = []

    def config_handler(request: httpx.Request) -> httpx.Response:
        config_requests.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"status": "ok"})

    config_client = ConfigAPIClient(
        config_settings,
        client_factory=lambda cfg: _build_httpx_client(cfg, httpx.MockTransport(config_handler)),
    )
    config_service = ConfigManagementService(config_client)
    config_service.validate(ConfigValidationRequest(payload={"files": []}, metadata={"actor": "tester"}))
    config_service.create_pr(ConfigPRRequest(payload={"branch": "feature"}, metadata={"actor": "tester"}))

    # Slack 通知のモック設定
    slack_settings = SlackConfig.from_mapping(
        {
            "webhook_url": "https://hooks.slack.com/services/T000/B000/XXXX",
            "channel": "#ml-ops",
            "username": "bot",
            "timeout_seconds": 2,
        }
    )

    slack_payloads: list[dict[str, object]] = []

    def slack_handler(request: httpx.Request) -> httpx.Response:
        slack_payloads.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200)

    slack_notifier = SlackWebhookNotifier(
        slack_settings,
        client=httpx.Client(timeout=slack_settings.timeout_seconds, transport=httpx.MockTransport(slack_handler)),
    )

    # Ops サービスとの連携検証
    audit_logger = DummyAuditLogger()
    ops_repository = InMemoryOpsFlagRepository()
    ops_service = OpsService(
        repository=ops_repository,
        audit_logger=audit_logger,
        notifier=slack_notifier,
    )

    response = ops_service.execute(OpsCommand(command="halt_global", arguments={}, metadata={"actor": "tester"}))
    assert response.status == "ok"
    assert ops_repository.get_snapshot().global_halt is True
    assert audit_logger.events[0][0] == "ops.halt_global"
    assert slack_payloads, "Slack 通知が送信されていること"

    # 後片付け
    slack_notifier.close()
    config_client.close()

    # Config API のモックリクエストが期待通りか検証
    assert config_requests[0]["metadata"]["actor"] == "tester"
    assert config_requests[1]["branch"] == "feature"

