"""
再学習全体をオーケストレートする Prefect フローのスケルトン。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from prefect import flow, get_run_logger

from ..services import BacktestRequest, BacktestResult, ThetaOptimizationRequest, ThetaOptimizationResult
from ..usecases import LearningRequest, LearningResponse, PublishRequest, PublishResponse
from .core_backtest import core_backtest_flow
from .core_publish import core_publish_flow
from .core_theta_opt import core_theta_opt_flow
from .dependencies import get_flow_dependencies


@dataclass(frozen=True)
class CoreRetrainResult:
    """
    core_retrain_flow の集約結果。
    """

    learning: LearningResponse
    backtest: BacktestResult | None
    theta: ThetaOptimizationResult | None
    publish: PublishResponse | None
    metadata: Mapping[str, str]


@flow(name="core_retrain_flow")
def core_retrain_flow(
    learning_request: LearningRequest,
    *,
    backtest_request: BacktestRequest | None = None,
    theta_request: ThetaOptimizationRequest | None = None,
    publish_request: PublishRequest | None = None,
    flow_metadata: Mapping[str, str] | None = None,
) -> CoreRetrainResult:
    """
    再学習 → バックテスト → θ最適化 → 配布 のシリアルチェーン。

    実運用では learning_request の結果をもとに backtest/theta/publish の
    リクエストを組み立てる。ここでは骨組みのみを提供し、具体的な生成処理は
    フロー呼び出し側で実装する。
    """

    logger = get_run_logger()
    logger.info("Starting core_retrain_flow")

    deps = get_flow_dependencies()

    learning_response = deps.learning_usecase.execute(learning_request)
    logger.info("Learning completed for model_version=%s", learning_response.model_artifact.model_version)

    backtest_result: BacktestResult | None = None
    if backtest_request is not None:
        logger.info("Running nested core_backtest_flow")
        backtest_result = core_backtest_flow(backtest_request)

    theta_result: ThetaOptimizationResult | None = None
    if theta_request is not None:
        logger.info("Running nested core_theta_opt_flow")
        theta_result = core_theta_opt_flow(theta_request)

    publish_result: PublishResponse | None = None
    if publish_request is not None:
        logger.info("Running nested core_publish_flow")
        publish_result = core_publish_flow(publish_request)

    aggregate = CoreRetrainResult(
        learning=learning_response,
        backtest=backtest_result,
        theta=theta_result,
        publish=publish_result,
        metadata=flow_metadata or {},
    )

    logger.info("core_retrain_flow completed")
    return aggregate

