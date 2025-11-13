"""
OPS コマンドユースケースのスケルトン。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Mapping, Protocol

from infrastructure.messaging import OpsFlagRepository, OpsFlagSnapshot, RedisPublisher


@dataclass(frozen=True)
class OpsCommand:
    """
    Ops コマンドの入力。
    """

    command: str
    arguments: Mapping[str, str]
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class OpsResponse:
    """
    Ops コマンドの実行結果。
    """

    status: str
    message: str
    details: Mapping[str, str] = field(default_factory=dict)


class OpsExecutor(Protocol):
    """
    実際の Ops 操作（ハルト、フラッテン等）を実行する。
    """

    def execute(self, command: str, arguments: Mapping[str, str]) -> str:
        ...


class OpsUseCase(Protocol):
    """
    Ops コマンドのハンドラ。
    """

    def execute(self, command: OpsCommand) -> OpsResponse:
        ...


class OpsAuditLogger(Protocol):
    """
    Ops 操作を監査ログとして記録する。
    """

    def log(self, event_name: str, payload: Mapping[str, str]) -> None:
        ...


class OpsNotifier(Protocol):
    """
    Ops 操作を外部通知するためのインターフェース。
    """

    def notify(self, message: str, *, title: str | None = None, fields: Mapping[str, str] | None = None) -> None:
        ...


class OpsService(OpsUseCase):
    """
    OpsCommand を受け付け、OpsFlagRepository を更新する実装。
    """

    def __init__(
        self,
        *,
        repository: OpsFlagRepository,
        audit_logger: OpsAuditLogger,
        event_publisher: RedisPublisher | None = None,
        ops_event_channel: str | None = None,
        notifier: OpsNotifier | None = None,
    ) -> None:
        self._repository = repository
        self._audit_logger = audit_logger
        self._event_publisher = event_publisher
        self._ops_event_channel = ops_event_channel
        self._notifier = notifier

    def execute(self, command: OpsCommand) -> OpsResponse:
        handler_name = command.command.lower()
        handler = getattr(self, f"_handle_{handler_name}", None)
        if handler is None or not callable(handler):
            return OpsResponse(status="error", message=f"Unsupported command '{command.command}'")

        response: OpsResponse = handler(command)
        self._audit_logger.log(
            event_name=f"ops.{handler_name}",
            payload={
                "status": response.status,
                "message": response.message,
                **command.metadata,
                **command.arguments,
            },
        )

        if self._event_publisher and self._ops_event_channel and response.status == "ok":
            event_payload = {
                "command": command.command,
                "arguments": command.arguments,
                "metadata": command.metadata,
                "status": response.status,
                "details": dict(response.details),
            }
            self._event_publisher.publish(self._ops_event_channel, json.dumps(event_payload))

        if self._notifier and response.status == "ok":
            fields = {
                "command": command.command,
                **{f"arg_{k}": v for k, v in command.arguments.items()},
                **response.details,
            }
            self._notifier.notify(
                message=response.message,
                title=f"ops.{handler_name}",
                fields=fields,
            )

        return response

    def _handle_status(self, _: OpsCommand) -> OpsResponse:
        snapshot = self._repository.get_snapshot()
        details = _snapshot_to_details(snapshot)
        return OpsResponse(status="ok", message="Ops status snapshot", details=details)

    def _handle_halt_global(self, command: OpsCommand) -> OpsResponse:
        self._repository.set_global_halt(True, reason=command.metadata.get("actor", "manual_halt"))
        snapshot = self._repository.get_snapshot()
        return OpsResponse(
            status="ok",
            message="Global trading halt activated.",
            details=_snapshot_to_details(snapshot),
        )

    def _handle_resume_global(self, command: OpsCommand) -> OpsResponse:
        self._repository.set_global_halt(False, reason=command.metadata.get("actor", "manual_resume"))
        snapshot = self._repository.get_snapshot()
        return OpsResponse(
            status="ok",
            message="Global trading halt disabled.",
            details=_snapshot_to_details(snapshot),
        )

    def _handle_halt_pairs(self, command: OpsCommand) -> OpsResponse:
        pairs = _split_csv(command.arguments.get("pairs", ""))
        if not pairs:
            return OpsResponse(status="error", message="pairs 引数が必要です。")
        self._repository.set_halted_pairs(pairs, reason=command.metadata.get("actor", "manual_halt_pairs"))
        snapshot = self._repository.get_snapshot()
        return OpsResponse(
            status="ok",
            message=f"Halted pairs updated: {', '.join(pairs)}",
            details=_snapshot_to_details(snapshot),
        )

    def _handle_flatten_pairs(self, command: OpsCommand) -> OpsResponse:
        pairs = _split_csv(command.arguments.get("pairs", ""))
        if not pairs:
            return OpsResponse(status="error", message="pairs 引数が必要です。")
        self._repository.set_flatten_pairs(pairs, reason=command.metadata.get("actor", "manual_flatten"))
        snapshot = self._repository.get_snapshot()
        return OpsResponse(
            status="ok",
            message=f"Flatten pairs updated: {', '.join(pairs)}",
            details=_snapshot_to_details(snapshot),
        )

    def _handle_set_leverage(self, command: OpsCommand) -> OpsResponse:
        leverage_str = command.arguments.get("leverage")
        if leverage_str is None:
            return OpsResponse(status="error", message="leverage 引数が必要です。")
        try:
            leverage_value = float(leverage_str)
        except ValueError as exc:
            return OpsResponse(status="error", message=f"leverage 引数が不正です: {exc}")
        if leverage_value <= 0:
            return OpsResponse(status="error", message="leverage は正の値でなければなりません。")

        self._repository.set_leverage_scale(leverage_value, reason=command.metadata.get("actor", "manual_leverage"))
        snapshot = self._repository.get_snapshot()
        return OpsResponse(
            status="ok",
            message=f"Leverage scale set to {leverage_value}",
            details=_snapshot_to_details(snapshot),
        )


class LoggingOpsAuditLogger(OpsAuditLogger):
    """
    logging.Logger を用いた監査ログ実装。
    """

    def __init__(self, logger_name: str = "ml_assets_core.audit.ops") -> None:
        self._logger = logging.getLogger(logger_name)

    def log(self, event_name: str, payload: Mapping[str, str]) -> None:
        self._logger.info("ops_event", extra={"event": event_name, "payload": dict(payload)})


def _split_csv(csv_values: str) -> list[str]:
    return [value.strip() for value in csv_values.split(",") if value.strip()]


def _snapshot_to_details(snapshot: OpsFlagSnapshot) -> Mapping[str, str]:
    return {
        "global_halt": str(snapshot.global_halt).lower(),
        "halted_pairs": ",".join(snapshot.halted_pairs),
        "flatten_pairs": ",".join(snapshot.flatten_pairs),
        "leverage_scale": f"{snapshot.leverage_scale:.6f}",
        **{f"meta_{k}": v for k, v in snapshot.metadata.items()},
    }

