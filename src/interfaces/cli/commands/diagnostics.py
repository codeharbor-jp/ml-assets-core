"""
診断用 CLI コマンド。
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, cast

import typer
from redis import Redis

from bootstrap.config_loader import YamlConfigLoader
from infrastructure.messaging import RedisMessagingConfig

app = typer.Typer(help="診断・ヘルスチェックコマンド")


@app.command("ping")
def ping() -> None:
    typer.echo("システム診断: OK")


@app.command("load-test-inference")
def load_test_inference(iterations: int = typer.Option(100, help="送信するリクエスト数")) -> None:
    """
    Redis キューに偽の推論リクエストを流し、ワーカーの負荷試験を行う。
    """

    project_root = Path(__file__).resolve().parents[4]
    config_bundle = YamlConfigLoader(project_root).load()
    messaging_section = cast(Mapping[str, object], config_bundle.require_section("messaging"))
    redis_mapping = cast(Mapping[str, object], messaging_section["redis"])
    messaging_config = RedisMessagingConfig.from_mapping(redis_mapping)

    redis_client = cast(Redis, Redis.from_url(messaging_config.url, decode_responses=True))

    payload = {
        "partition_ids": ["EURUSD", "USDJPY"],
        "theta_params": {
            "theta1": 0.7,
            "theta2": 0.3,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": "load-test",
            "source_model_version": "diagnostics",
        },
        "metadata": {"source": "cli-load-test"},
    }

    start = time.perf_counter()
    for _ in range(iterations):
        redis_client.publish(messaging_config.inference_request_channel, json.dumps(payload))
    duration = time.perf_counter() - start

    typer.echo(
        f"Published {iterations} inference requests to '{messaging_config.inference_request_channel}' "
        f"in {duration:.3f} seconds ({iterations / duration:.2f} req/s)."
    )

