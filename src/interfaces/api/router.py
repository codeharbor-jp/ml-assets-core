"""
FastAPI アプリケーションのルート設定。
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, FastAPI

from application.services import MetricsQuery, ThetaOptimizationRequest, TrainingRequest
from application.usecases import InferenceRequest, PublishRequest
from interfaces.api.deps import APIContainer
from interfaces.api.schemas import (
    BacktestRequestSchema,
    BacktestResponseSchema,
    ConfigApplyRequestSchema,
    ConfigApproveRequestSchema,
    ConfigMergeRequestSchema,
    ConfigOperationResponseSchema,
    ConfigPRRequestSchema,
    ConfigRollbackRequestSchema,
    ConfigValidateRequestSchema,
    InferenceRequestSchema,
    InferenceResponseSchema,
    MetricsResponseSchema,
    OpsCommandSchema,
    OpsResponseSchema,
    PublishRequestSchema,
    PublishResponseSchema,
    ReportGenerateRequestSchema,
    ReportGenerateResponseSchema,
    ThetaOptimizationRequestSchema,
    ThetaOptimizationResponseSchema,
    TrainingRequestSchema,
    TrainingResponseSchema,
)


def create_api_app() -> FastAPI:
    app = FastAPI(title="ml-assets-core API")
    app.include_router(_create_router(), prefix="/api/v1")
    return app


def _create_router() -> APIRouter:
    router = APIRouter()

    @router.post("/learning/train", response_model=TrainingResponseSchema)
    def run_training(payload: TrainingRequestSchema):
        deps = APIContainer.resolve()
        request = TrainingRequest(
            partition=payload.partition,
            features=payload.features,
            labels_ai1=payload.labels_ai1,
            labels_ai2=payload.labels_ai2,
            params_ai1=payload.params_ai1,
            params_ai2=payload.params_ai2,
            calibration=payload.calibration,
            random_seed=payload.random_seed,
            metadata=payload.metadata,
        )
        result = deps.trainer_service.run(request)
        return TrainingResponseSchema.from_result(result)

    @router.post("/learning/backtest", response_model=BacktestResponseSchema)
    def run_backtest(payload: BacktestRequestSchema):
        deps = APIContainer.resolve()
        request = payload.to_domain()
        result = deps.backtester_service.run(request)
        return BacktestResponseSchema.from_result(result)

    @router.post("/learning/theta-opt", response_model=ThetaOptimizationResponseSchema)
    def run_theta_opt(payload: ThetaOptimizationRequestSchema):
        deps = APIContainer.resolve()
        request = ThetaOptimizationRequest(
            range=payload.range,
            initial_params=payload.initial_params,
            plan=payload.plan,
            score_history=payload.score_history,
            metadata=payload.metadata,
        )
        result = deps.theta_optimizer.optimize(request)
        return ThetaOptimizationResponseSchema.from_result(result)

    @router.post("/inference/run", response_model=InferenceResponseSchema)
    def run_inference(payload: InferenceRequestSchema):
        deps = APIContainer.resolve()
        request = InferenceRequest(
            partition_ids=payload.partition_ids,
            theta_params=payload.theta_params,
            metadata=payload.metadata,
        )
        result = deps.inference_usecase.execute(request)
        return InferenceResponseSchema.from_result(result)

    @router.post("/publish", response_model=PublishResponseSchema)
    def publish(payload: PublishRequestSchema):
        deps = APIContainer.resolve()
        request = PublishRequest(
            artifact=payload.artifact,
            theta_params=payload.theta_params,
            metadata=payload.metadata,
        )
        response = deps.publish_usecase.execute(request)
        return PublishResponseSchema.from_response(response)

    @router.post("/ops", response_model=OpsResponseSchema)
    def handle_ops(payload: OpsCommandSchema):
        deps = APIContainer.resolve()
        response = deps.ops_usecase.execute(payload.to_domain())
        return OpsResponseSchema.from_response(response)

    @router.post("/configs/validate", response_model=ConfigOperationResponseSchema)
    def validate_configs(payload: ConfigValidateRequestSchema):
        deps = APIContainer.resolve()
        result = deps.config_usecase.validate(payload.to_domain())
        return ConfigOperationResponseSchema.from_result(result)

    @router.post("/configs/pr", response_model=ConfigOperationResponseSchema)
    def create_config_pr(payload: ConfigPRRequestSchema):
        deps = APIContainer.resolve()
        result = deps.config_usecase.create_pr(payload.to_domain())
        return ConfigOperationResponseSchema.from_result(result)

    @router.post("/configs/approve", response_model=ConfigOperationResponseSchema)
    def approve_config_pr(payload: ConfigApproveRequestSchema):
        deps = APIContainer.resolve()
        result = deps.config_usecase.approve(payload.to_domain())
        return ConfigOperationResponseSchema.from_result(result)

    @router.post("/configs/merge", response_model=ConfigOperationResponseSchema)
    def merge_config_pr(payload: ConfigMergeRequestSchema):
        deps = APIContainer.resolve()
        result = deps.config_usecase.merge(payload.to_domain())
        return ConfigOperationResponseSchema.from_result(result)

    @router.post("/configs/apply", response_model=ConfigOperationResponseSchema)
    def apply_config(payload: ConfigApplyRequestSchema):
        deps = APIContainer.resolve()
        result = deps.config_usecase.apply(payload.to_domain())
        return ConfigOperationResponseSchema.from_result(result)

    @router.post("/configs/rollback", response_model=ConfigOperationResponseSchema)
    def rollback_config(payload: ConfigRollbackRequestSchema):
        deps = APIContainer.resolve()
        result = deps.config_usecase.rollback(payload.to_domain())
        return ConfigOperationResponseSchema.from_result(result)

    @router.get("/metrics/model", response_model=MetricsResponseSchema)
    def get_model_metrics(from_ts: datetime | None = None, to_ts: datetime | None = None):
        deps = APIContainer.resolve()
        payload = deps.analytics_service.get_model_metrics(MetricsQuery(start=from_ts, end=to_ts))
        return MetricsResponseSchema.from_payload(payload)

    @router.get("/metrics/trading", response_model=MetricsResponseSchema)
    def get_trading_metrics(
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
        pair_id: str | None = None,
    ):
        deps = APIContainer.resolve()
        payload = deps.analytics_service.get_trading_metrics(
            MetricsQuery(start=from_ts, end=to_ts, pair_id=pair_id),
        )
        return MetricsResponseSchema.from_payload(payload)

    @router.get("/metrics/data-quality", response_model=MetricsResponseSchema)
    def get_data_quality_metrics(from_ts: datetime | None = None, to_ts: datetime | None = None):
        deps = APIContainer.resolve()
        payload = deps.analytics_service.get_data_quality_metrics(MetricsQuery(start=from_ts, end=to_ts))
        return MetricsResponseSchema.from_payload(payload)

    @router.get("/metrics/risk", response_model=MetricsResponseSchema)
    def get_risk_metrics(from_ts: datetime | None = None, to_ts: datetime | None = None):
        deps = APIContainer.resolve()
        payload = deps.analytics_service.get_risk_metrics(MetricsQuery(start=from_ts, end=to_ts))
        return MetricsResponseSchema.from_payload(payload)

    @router.post("/reports/generate", response_model=ReportGenerateResponseSchema)
    def generate_report(payload: ReportGenerateRequestSchema):
        deps = APIContainer.resolve()
        query = payload.to_query()
        result = deps.analytics_service.generate_report(payload.report_type, query)
        return ReportGenerateResponseSchema.from_payload(payload.report_type, result)

    return router

