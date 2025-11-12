"""
診断用 CLI コマンド。
"""

from __future__ import annotations

import typer

app = typer.Typer(help="診断・ヘルスチェックコマンド")


@app.command("ping")
def ping() -> None:
    typer.echo("システム診断: OK")

