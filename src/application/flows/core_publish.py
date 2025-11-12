"""
モデル配布フローのスケルトン。
"""

from __future__ import annotations

from prefect import flow, get_run_logger

from ..usecases import PublishRequest, PublishResponse
from .dependencies import get_flow_dependencies


@flow(name="core_publish_flow")
def core_publish_flow(request: PublishRequest) -> PublishResponse:
    """
    model_registry 更新・通知処理を統括するフロー。
    """

    logger = get_run_logger()
    logger.info(
        "Starting core_publish_flow for model_version=%s",
        request.artifact.model_version,
    )

    deps = get_flow_dependencies()
    response = deps.publish_usecase.execute(request)

    logger.info("Completed core_publish_flow status=%s audit=%s", response.status, response.audit_record_id)
    return response

