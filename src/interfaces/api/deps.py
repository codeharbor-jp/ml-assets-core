"""
FastAPI 用の依存性定義。
"""

from __future__ import annotations

from dataclasses import dataclass

from application import AnalyticsService, BacktesterService, DatasetCatalogBuilder, ThetaOptimizationService, TrainerService
from application.usecases import (
    ConfigManagementUseCase,
    InferenceUseCase,
    LearningUseCase,
    OpsUseCase,
    PublishUseCase,
)


@dataclass
class ApiDependencies:
    """
    API レイヤーが利用する依存関係。
    """

    learning_usecase: LearningUseCase
    inference_usecase: InferenceUseCase
    publish_usecase: PublishUseCase
    ops_usecase: OpsUseCase
    config_usecase: ConfigManagementUseCase
    trainer_service: TrainerService
    backtester_service: BacktesterService
    theta_optimizer: ThetaOptimizationService
    catalog_builder: DatasetCatalogBuilder
    analytics_service: AnalyticsService


class APIContainer:
    """
    依存性をグローバルに保持する簡易 DI コンテナ。
    """

    _deps: ApiDependencies | None = None

    @classmethod
    def configure(cls, deps: ApiDependencies) -> None:
        cls._deps = deps

    @classmethod
    def resolve(cls) -> ApiDependencies:
        if cls._deps is None:
            raise RuntimeError("API 依存性が未設定です。configure_dependencies を実行してください。")
        return cls._deps


def configure_dependencies(deps: ApiDependencies) -> None:
    APIContainer.configure(deps)

