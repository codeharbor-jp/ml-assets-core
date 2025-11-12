"""
Typer ベースの CLI スケルトン。
"""

from __future__ import annotations

import typer

from .commands import diagnostics, flow, ops


def create_cli() -> typer.Typer:
    app = typer.Typer(help="ml-assets-core CLI")
    app.add_typer(flow.app, name="flow")
    app.add_typer(ops.app, name="ops")
    app.add_typer(diagnostics.app, name="diagnostics")
    return app

