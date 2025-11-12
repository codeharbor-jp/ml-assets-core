"""
バックテスト専用フローのスケルトン。
"""

from __future__ import annotations

from prefect import flow, get_run_logger

from ..services import BacktestRequest, BacktestResult
from .dependencies import get_flow_dependencies


@flow(name="core_backtest_flow")
def core_backtest_flow(request: BacktestRequest) -> BacktestResult:
    """
    backtest-assets-engine を呼び出し、ストレス評価結果を返却するフロー。
    """

    logger = get_run_logger()
    logger.info("Starting core_backtest_flow for model_version=%s", request.model_artifact.model_version)

    deps = get_flow_dependencies()
    result = deps.backtester_service.run(request)

    logger.info("Completed core_backtest_flow with summary keys=%s", list(result.summary_metrics.keys()))
    return result

