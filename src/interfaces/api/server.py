from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Mapping, Sequence

from fastapi import HTTPException

from application import AnalyticsService
from application.services import (
    BacktestRequest,
    BacktestResult,
    BacktesterService,
    DatasetCatalogBuilder,
    ThetaOptimizationResult,
)
from application.services.analytics import AnalyticsRepository, MetricsPayload, MetricsQuery
from application.services.theta_optimizer import ThetaOptimizationRequest, ThetaOptimizationService
from application.services.trainer import TrainerService, TrainingRequest, TrainingResult
from application.usecases import (
    ConfigApplyRequest,
    ConfigApproveRequest,
    ConfigManagementUseCase,
    ConfigMergeRequest,
    ConfigOperationResult,
    ConfigPRRequest,
    ConfigRollbackRequest,
    ConfigValidationRequest,
    InferenceRequest,
    InferenceResponse,
    InferenceUseCase,
    LearningRequest,
    LearningResponse,
    LearningUseCase,
    OpsCommand,
    OpsResponse,
    OpsUseCase,
    PublishRequest,
    PublishResponse,
    PublishUseCase,
)
from domain import DatasetPartition, Signal, SignalLeg, TradeSide
from interfaces.api import create_api_app
from interfaces.api.deps import ApiDependencies, configure_dependencies
from runtime.dependencies import build_backtest_components, build_theta_components


class _UnimplementedLearningUseCase(LearningUseCase):
    def execute(self, request: LearningRequest) -> LearningResponse:  # noqa: ARG002
        raise HTTPException(status_code=501, detail="learning_usecase is not available in the dev server.")


class _StubInferenceUseCase(InferenceUseCase):
    def execute(self, request: InferenceRequest) -> InferenceResponse:  # noqa: ARG002
        timestamp = datetime.now(timezone.utc)
        signal = Signal(
            signal_id="dev-signal",
            timestamp=timestamp,
            pair_id="EURUSD",
            legs=[SignalLeg(symbol="EURUSD", side=TradeSide.LONG, beta_weight=1.0, notional=100000.0)],
            return_prob=0.5,
            risk_score=0.5,
            theta1=0.7,
            theta2=0.3,
            position_scale=1.0,
            model_version="dev",
            valid_until=timestamp + timedelta(minutes=5),
        )
        return InferenceResponse(signals=[signal], diagnostics={"notice": "stub response"})


class _UnimplementedPublishUseCase(PublishUseCase):
    def execute(self, request: PublishRequest) -> PublishResponse:  # noqa: ARG002
        raise HTTPException(status_code=501, detail="publish_usecase is not available in the dev server.")


class _UnimplementedOpsUseCase(OpsUseCase):
    def execute(self, command: OpsCommand) -> OpsResponse:  # noqa: ARG002
        raise HTTPException(status_code=501, detail="ops_usecase is not available in the dev server.")


class _UnimplementedConfigUseCase(ConfigManagementUseCase):
    def validate(self, request: ConfigValidationRequest) -> ConfigOperationResult:  # noqa: ARG002
        raise HTTPException(status_code=501, detail="config_usecase is not available in the dev server.")

    def create_pr(self, request: ConfigPRRequest) -> ConfigOperationResult:  # noqa: ARG002
        raise HTTPException(status_code=501, detail="config_usecase is not available in the dev server.")

    def approve(self, request: ConfigApproveRequest) -> ConfigOperationResult:  # noqa: ARG002
        raise HTTPException(status_code=501, detail="config_usecase is not available in the dev server.")

    def merge(self, request: ConfigMergeRequest) -> ConfigOperationResult:  # noqa: ARG002
        raise HTTPException(status_code=501, detail="config_usecase is not available in the dev server.")

    def apply(self, request: ConfigApplyRequest) -> ConfigOperationResult:  # noqa: ARG002
        raise HTTPException(status_code=501, detail="config_usecase is not available in the dev server.")

    def rollback(self, request: ConfigRollbackRequest) -> ConfigOperationResult:  # noqa: ARG002
        raise HTTPException(status_code=501, detail="config_usecase is not available in the dev server.")


class _UnimplementedTrainerService(TrainerService):
    def run(self, request: TrainingRequest) -> TrainingResult:  # noqa: ARG002
        raise HTTPException(status_code=501, detail="trainer_service is not available in the dev server.")


class _UnimplementedBacktesterService(BacktesterService):
    def run(self, request: BacktestRequest) -> BacktestResult:  # noqa: ARG002
        raise HTTPException(status_code=501, detail="backtester_service is not available in the dev server.")


class _UnimplementedThetaOptimizer(ThetaOptimizationService):
    def optimize(self, request: ThetaOptimizationRequest) -> ThetaOptimizationResult:  # noqa: ARG002
        raise HTTPException(status_code=501, detail="theta_optimizer is not available in the dev server.")


class _StubDatasetCatalogBuilder(DatasetCatalogBuilder):
    def __init__(self) -> None:  # type: ignore[super-init-not-called]
        pass

    def build(self, partitions: Sequence[DatasetPartition], *, thresholds: Mapping[str, float]):  # noqa: ARG002
        raise HTTPException(status_code=501, detail="dataset_catalog_builder is not available in the dev server.")


class _StubAnalyticsRepository(AnalyticsRepository):
    def fetch_model_metrics(self, query: MetricsQuery) -> Sequence[Mapping[str, object]]:  # noqa: ARG002
        return [{"metric": "sharpe", "value": 1.23}]

    def fetch_trading_metrics(self, query: MetricsQuery) -> Sequence[Mapping[str, object]]:  # noqa: ARG002
        return [{"metric": "pnl", "value": 5000.0}]

    def fetch_data_quality_metrics(self, query: MetricsQuery) -> Sequence[Mapping[str, object]]:  # noqa: ARG002
        return [{"metric": "missing_rate", "value": 0.0}]

    def fetch_risk_metrics(self, query: MetricsQuery) -> Sequence[Mapping[str, object]]:  # noqa: ARG002
        return [{"metric": "risk_score", "value": 0.2}]


class _StubAnalyticsService(AnalyticsService):
    def __init__(self) -> None:
        super().__init__(_StubAnalyticsRepository())


def _configure_dependencies() -> None:
    analytics_service = _StubAnalyticsService()
    logger = logging.getLogger("interfaces.api.server")

    backtester_service: BacktesterService = _UnimplementedBacktesterService()
    theta_optimizer: ThetaOptimizationService = _UnimplementedThetaOptimizer()

    try:
        backtest_components = build_backtest_components()
        backtester_service = backtest_components.service
    except Exception as exc:  # pragma: no cover - 環境依存
        logger.warning("Failed to initialize BacktesterService: %s", exc, exc_info=True)

    try:
        theta_components = build_theta_components()
        theta_optimizer = theta_components.service
    except Exception as exc:  # pragma: no cover - 環境依存
        logger.warning("Failed to initialize ThetaOptimizationService: %s", exc, exc_info=True)

    deps = ApiDependencies(
        learning_usecase=_UnimplementedLearningUseCase(),
        inference_usecase=_StubInferenceUseCase(),
        publish_usecase=_UnimplementedPublishUseCase(),
        ops_usecase=_UnimplementedOpsUseCase(),
        config_usecase=_UnimplementedConfigUseCase(),
        trainer_service=_UnimplementedTrainerService(),
        backtester_service=backtester_service,
        theta_optimizer=theta_optimizer,
        catalog_builder=_StubDatasetCatalogBuilder(),
        analytics_service=analytics_service,
    )
    configure_dependencies(deps)


_configure_dependencies()
app = create_api_app()
