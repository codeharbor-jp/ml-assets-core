"""
FastAPI アプリケーションのルート設定。
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

from ...application.services import BacktestRequest, ThetaOptimizationRequest, TrainingRequest
from ...application.usecases import InferenceRequest, PublishRequest
from .deps import APIContainer
from .schemas import (
    BacktestRequestSchema,
    BacktestResponseSchema,
    InferenceRequestSchema,
    InferenceResponseSchema,
    OpsCommandSchema,
    OpsResponseSchema,
    PublishRequestSchema,
    PublishResponseSchema,
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
        request = BacktestRequest(
            model_artifact=payload.model_artifact,
            params=payload.params,
            engine_config=payload.engine_config,
            stress_scenarios=payload.stress_scenarios,
            metadata=payload.metadata,
        )
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

    return router

