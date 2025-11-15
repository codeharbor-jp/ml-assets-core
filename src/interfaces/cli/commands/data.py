"""
データ関連 CLI コマンド。
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from runtime import build_storage_resolver

app = typer.Typer(help="データセット操作コマンド")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET = PROJECT_ROOT / "samples" / "data" / "sample_canonical.json"
DEFAULT_EXPECTATIONS = PROJECT_ROOT / "samples" / "data" / "expectations.yaml"


@app.command("seed-sample")
def seed_sample(
    *,
    env: str = typer.Option("dev", "--env", help="SERVICE_ENV"),
    timeframe: str = typer.Option("1h", "--timeframe", help="時間軸 (例: 1h)"),
    symbol: str = typer.Option("EURUSD", "--symbol", help="銘柄シンボル"),
    month: str = typer.Option("2025-01", "--month", help="YYYY-MM 形式"),
    dataset: Path = typer.Option(DEFAULT_DATASET, "--dataset", help="投入する canonical JSON"),
    expectations: Path = typer.Option(
        DEFAULT_EXPECTATIONS, "--expectations", help="DQ 期待値 YAML"
    ),
    output_root: Path | None = typer.Option(
        None,
        "--output-root",
        help="canonical_root を明示的に上書き (テスト用)",
    ),
    force: bool = typer.Option(False, "--force", help="既存ファイルを上書き"),
) -> None:
    """
    サンプルデータセットを storage.canonical_root にコピーする。
    """

    if not dataset.exists():
        raise typer.BadParameter(f"dataset が存在しません: {dataset}")
    if not expectations.exists():
        raise typer.BadParameter(f"expectations が存在しません: {expectations}")

    try:
        json.loads(dataset.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"dataset が JSON として不正です: {exc}") from exc

    canonical_root = _resolve_canonical_root(env=env, output_root=output_root)
    target_dir = canonical_root / timeframe / symbol / month
    target_file = target_dir / "canonical.json"
    expectations_file = target_dir / "dq_expectations.yaml"

    if target_file.exists() and not force:
        raise typer.BadParameter(
            f"{target_file} は既に存在します。--force で上書きしてください。"
        )

    target_dir.mkdir(parents=True, exist_ok=True)
    target_file.write_text(dataset.read_text(encoding="utf-8"), encoding="utf-8")
    expectations_file.write_text(expectations.read_text(encoding="utf-8"), encoding="utf-8")

    typer.secho(
        f"Sample dataset written to {target_file}\n"
        f"DQ expectations written to {expectations_file}",
        fg=typer.colors.GREEN,
    )


def _resolve_canonical_root(*, env: str, output_root: Path | None) -> Path:
    if output_root is not None:
        output_root.mkdir(parents=True, exist_ok=True)
        return output_root

    resolver = build_storage_resolver(environment=env)
    return Path(resolver.resolve("canonical_root"))

