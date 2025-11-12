"""
フロー関連 CLI コマンド。
"""

from __future__ import annotations

import typer

from ...application.flows import CoreRetrainResult, core_backtest_flow, core_retrain_flow, core_theta_opt_flow
from ...application.services import BacktestRequest, ThetaOptimizationRequest
from ...application.usecases import LearningRequest

app = typer.Typer(help="Prefect フロー操作コマンド")


@app.command("retrain")
def retrain() -> None:
    """
    再学習フローを手動実行（スケルトン）。
    """

    typer.echo("core_retrain_flow を実行するには LearningRequest を構築してください。")


@app.command("backtest")
def backtest() -> None:
    typer.echo("core_backtest_flow を実行するには BacktestRequest を構築してください。")


@app.command("theta-opt")
def theta_opt() -> None:
    typer.echo("core_theta_opt_flow を実行するには ThetaOptimizationRequest を構築してください。")

