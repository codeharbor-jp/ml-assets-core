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
    ThetaOptimizationResult,
)
from application.services.analytics import AnalyticsRepository, MetricsPayload, MetricsQuery
from application.services.theta_optimizer import ThetaOptimizationRequest, ThetaOptimizationService
from application.services.trainer import TrainerService, TrainingRequest, TrainingResult
from application.services.dataset_catalog_builder import (
    DatasetCatalogBuilder,
    DataQualityEvaluator,
    MetadataLoader,
)
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
from domain import DataQualitySnapshot, DatasetPartition, Signal, SignalLeg, TradeSide
from interfaces.api import create_api_app
from interfaces.api.deps import ApiDependencies, configure_dependencies
from runtime.dependencies import (
    build_analytics_service,
    build_backtest_components,
    build_config_management_service,
    build_learning_components,
    build_ops_usecase,
    build_publish_components,
    build_theta_components,
)


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
    class _MetadataLoader(MetadataLoader):
        def load_snapshot(self, partition: DatasetPartition) -> DataQualitySnapshot:  # noqa: ARG002
            raise HTTPException(status_code=501, detail="dataset_catalog_builder is not available in the dev server.")

        def load_metadata(self, partition: DatasetPartition) -> Mapping[str, str]:  # noqa: ARG002
            raise HTTPException(status_code=501, detail="dataset_catalog_builder is not available in the dev server.")

    class _DQEvaluator(DataQualityEvaluator):
        def evaluate(self, snapshot: DataQualitySnapshot, thresholds: Mapping[str, float]):  # noqa: ARG002
            raise HTTPException(status_code=501, detail="dataset_catalog_builder is not available in the dev server.")

    def __init__(self) -> None:
        super().__init__(metadata_loader=self._MetadataLoader(), dq_evaluator=self._DQEvaluator())

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
    logger = logging.getLogger("interfaces.api.server")

    analytics_service: AnalyticsService = _StubAnalyticsService()
    learning_usecase: LearningUseCase = _UnimplementedLearningUseCase()
    trainer_service: TrainerService = _UnimplementedTrainerService()
    publish_usecase: PublishUseCase = _UnimplementedPublishUseCase()
    ops_usecase: OpsUseCase = _UnimplementedOpsUseCase()
    config_usecase: ConfigManagementUseCase = _UnimplementedConfigUseCase()
    backtester_service: BacktesterService = _UnimplementedBacktesterService()
    theta_optimizer: ThetaOptimizationService = _UnimplementedThetaOptimizer()

    try:
        analytics_service = build_analytics_service()
    except Exception as exc:  # pragma: no cover - 環境依存
        logger.warning("Failed to initialize AnalyticsService: %s", exc, exc_info=True)

    try:
        learning_components = build_learning_components()
        learning_usecase = learning_components.usecase
        trainer_service = learning_components.trainer
    except Exception as exc:  # pragma: no cover - 環境依存
        logger.warning("Failed to initialize Learning components: %s", exc, exc_info=True)

    try:
        publish_components = build_publish_components()
        publish_usecase = publish_components.service
    except Exception as exc:  # pragma: no cover - 環境依存
        logger.warning("Failed to initialize PublishUseCase: %s", exc, exc_info=True)

    try:
        ops_usecase = build_ops_usecase()
    except Exception as exc:  # pragma: no cover - 環境依存
        logger.warning("Failed to initialize OpsUseCase: %s", exc, exc_info=True)

    try:
        config_usecase = build_config_management_service()
    except Exception as exc:  # pragma: no cover - 環境依存
        logger.warning("Failed to initialize ConfigManagementUseCase: %s", exc, exc_info=True)

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
        learning_usecase=learning_usecase,
        inference_usecase=_StubInferenceUseCase(),
        publish_usecase=publish_usecase,
        ops_usecase=ops_usecase,
        config_usecase=config_usecase,
        trainer_service=trainer_service,
        backtester_service=backtester_service,
        theta_optimizer=theta_optimizer,
        catalog_builder=_StubDatasetCatalogBuilder(),
        analytics_service=analytics_service,
    )
    configure_dependencies(deps)


_configure_dependencies()
app = create_api_app()
