from __future__ import annotations

from unittest.mock import MagicMock

from application.usecases.configs import (
    ConfigApplyRequest,
    ConfigApproveRequest,
    ConfigManagementService,
    ConfigMergeRequest,
    ConfigPRRequest,
    ConfigRollbackRequest,
    ConfigValidationRequest,
)


def test_config_management_service_validate_merges_metadata() -> None:
    client = MagicMock()
    client.validate.return_value = {"status": "validated"}
    service = ConfigManagementService(client)

    request = ConfigValidationRequest(payload={"files": []}, metadata={"actor": "tester"})
    result = service.validate(request)

    client.validate.assert_called_once()
    sent_payload = client.validate.call_args.kwargs.get("payload") or client.validate.call_args.args[0]
    assert sent_payload["metadata"]["actor"] == "tester"
    assert result.action == "validate"
    assert result.payload["status"] == "validated"


def test_config_management_service_operation_methods_delegate() -> None:
    client = MagicMock()
    client.create_pr.return_value = {"id": "pr-1"}
    client.approve.return_value = {"status": "approved"}
    client.merge.return_value = {"status": "merged"}
    client.apply.return_value = {"status": "applied"}
    client.rollback.return_value = {"status": "rolled_back"}

    service = ConfigManagementService(client)

    pr_result = service.create_pr(ConfigPRRequest(payload={"branch": "feature"}, metadata={}))
    approve_result = service.approve(ConfigApproveRequest(pr_id="pr-1", comment="ok"))
    merge_result = service.merge(ConfigMergeRequest(pr_id="pr-1"))
    apply_result = service.apply(ConfigApplyRequest(pr_id="pr-1"))
    rollback_result = service.rollback(ConfigRollbackRequest(pr_id="pr-1", reason="issue"))

    assert pr_result.action == "create_pr"
    assert approve_result.payload["status"] == "approved"
    assert merge_result.payload["status"] == "merged"
    assert apply_result.payload["status"] == "applied"
    assert rollback_result.payload["status"] == "rolled_back"

    client.create_pr.assert_called_once()
    client.approve.assert_called_once_with("pr-1", comment="ok")
    client.merge.assert_called_once_with("pr-1")
    client.apply.assert_called_once_with("pr-1")
    client.rollback.assert_called_once_with("pr-1", reason="issue")

