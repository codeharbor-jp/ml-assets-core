"""
Config API との連携クライアント。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, MutableMapping, cast

import httpx


class ConfigAPIError(RuntimeError):
    """Config API 呼び出し失敗時の例外。"""


@dataclass(frozen=True)
class ConfigAPISettings:
    """
    Config API 呼び出しに必要な設定値。
    """

    base_url: str
    api_token: str | None
    timeout_seconds: float
    retries: int
    verify_ssl: bool

    @staticmethod
    def from_mapping(mapping: Mapping[str, object]) -> "ConfigAPISettings":
        try:
            raw_base_url = mapping["base_url"]
        except KeyError as exc:
            raise ValueError("config_api.base_url が設定されていません。") from exc

        if raw_base_url in (None, ""):
            raise ValueError("config_api.base_url は環境設定で必須です。")

        base_url = str(raw_base_url)
        api_token = mapping.get("api_token")
        timeout_seconds = _to_float(mapping.get("timeout_seconds", 10.0), name="timeout_seconds")
        retries = _to_int(mapping.get("retries", 3), name="retries")
        verify_ssl = bool(mapping.get("verify_ssl", True))

        if retries <= 0:
            raise ValueError("retries は 1 以上で指定してください。")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds は正の値である必要があります。")

        token = str(api_token) if api_token not in (None, "") else None
        return ConfigAPISettings(
            base_url=base_url,
            api_token=token,
            timeout_seconds=timeout_seconds,
            retries=retries,
            verify_ssl=verify_ssl,
        )


class ConfigAPIClient:
    """
    Config API への HTTP リクエストを担当するクライアント。
    """

    def __init__(
        self,
        settings: ConfigAPISettings,
        *,
        client_factory: Callable[[ConfigAPISettings], httpx.Client] | None = None,
    ) -> None:
        self._settings = settings
        factory = client_factory or _default_client_factory
        self._client = factory(settings)

    def close(self) -> None:
        """
        生成した HTTP クライアントをクローズする。
        """

        self._client.close()

    def validate(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        return self._post("/configs/validate", payload)

    def create_pr(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        return self._post("/configs/pr", payload)

    def approve(self, pr_id: str, *, comment: str | None = None) -> Mapping[str, object]:
        request_payload: MutableMapping[str, object] = {"pr_id": pr_id}
        if comment:
            request_payload["comment"] = comment
        return self._post("/configs/approve", request_payload)

    def merge(self, pr_id: str) -> Mapping[str, object]:
        return self._post("/configs/merge", {"pr_id": pr_id})

    def apply(self, pr_id: str) -> Mapping[str, object]:
        return self._post("/configs/apply", {"pr_id": pr_id})

    def rollback(self, pr_id: str, *, reason: str | None = None) -> Mapping[str, object]:
        request_payload: MutableMapping[str, object] = {"pr_id": pr_id}
        if reason:
            request_payload["reason"] = reason
        return self._post("/configs/rollback", request_payload)

    def _post(self, path: str, payload: Mapping[str, object]) -> Mapping[str, object]:
        last_exc: Exception | None = None
        for attempt in range(1, self._settings.retries + 1):
            try:
                response = self._client.post(path, json=payload)
                response.raise_for_status()
                if not response.headers.get("content-type", "").startswith("application/json"):
                    return {"status": response.status_code}
                return cast(Mapping[str, object], response.json())
            except httpx.HTTPStatusError as exc:
                raise ConfigAPIError(
                    f"Config API 呼び出しに失敗しました (status={exc.response.status_code}, path={path})"
                ) from exc
            except httpx.HTTPError as exc:
                last_exc = exc
        raise ConfigAPIError(f"Config API へのリクエストに失敗しました (path={path})") from last_exc


def _default_client_factory(settings: ConfigAPISettings) -> httpx.Client:
    headers = {}
    if settings.api_token:
        headers["Authorization"] = f"Bearer {settings.api_token}"
    return httpx.Client(
        base_url=settings.base_url,
        timeout=settings.timeout_seconds,
        verify=settings.verify_ssl,
        headers=headers,
    )


def _to_int(value: object, *, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} は真偽値ではなく整数で指定してください。")
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        return int(value)
    raise ValueError(f"{name} は整数で指定してください。")


def _to_float(value: object, *, name: str) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value)
    raise ValueError(f"{name} は数値で指定してください。")

