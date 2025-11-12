"""
Ops 関連 CLI コマンド。
"""

from __future__ import annotations

import typer

app = typer.Typer(help="Ops コマンド")


@app.command("halt")
def halt(global_halt: bool = typer.Option(True, "--global/--no-global")) -> None:
    typer.echo(f"global_halt={global_halt} を設定するには OpsUseCase を呼び出してください。")


@app.command("resume")
def resume() -> None:
    typer.echo("OpsUseCase の resume 処理を実装してください。")

