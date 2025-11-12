"""
Prefect フローが利用する依存関係を管理するモジュール。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..services import BacktesterService, ThetaOptimizationService
from ..usecases import InferenceUseCase, LearningUseCase, OpsUseCase, PublishUseCase


@dataclass
class FlowDependencies:
    """
    Prefect フロー内で使用するユースケース・サービス群。
    """

    learning_usecase: LearningUseCase
    inference_usecase: InferenceUseCase
    publish_usecase: PublishUseCase
    ops_usecase: OpsUseCase
    backtester_service: BacktesterService
    theta_optimizer: ThetaOptimizationService


_dependencies: FlowDependencies | None = None


def configure_flow_dependencies(deps: FlowDependencies) -> None:
    """
    フロー実行前に依存関係を登録する。
    """

    global _dependencies
    _dependencies = deps


def get_flow_dependencies() -> FlowDependencies:
    """
    登録済みの依存関係を取得する。
    """

    if _dependencies is None:
        raise RuntimeError("FlowDependencies が未設定です。configure_flow_dependencies() を実行してください。")
    return _dependencies

