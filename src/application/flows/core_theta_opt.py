"""
θ最適化フローのスケルトン。
"""

from __future__ import annotations

from prefect import flow, get_run_logger

from ..services import ThetaOptimizationRequest, ThetaOptimizationResult
from .dependencies import get_flow_dependencies


@flow(name="core_theta_opt_flow")
def core_theta_opt_flow(request: ThetaOptimizationRequest) -> ThetaOptimizationResult:
    """
    粗グリッド探索→Optuna探索を実行し、最適化結果を返却する。
    """

    logger = get_run_logger()
    logger.info(
        "Starting core_theta_opt_flow with range θ1[%s,%s] θ2[%s,%s]",
        request.range.theta1_min,
        request.range.theta1_max,
        request.range.theta2_min,
        request.range.theta2_max,
    )

    deps = get_flow_dependencies()
    result = deps.theta_optimizer.optimize(request)

    logger.info("Completed core_theta_opt_flow with score=%s", result.score)
    return result

