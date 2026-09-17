"""Integration coverage for failed workflow execution through the HTTP API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.integration.fixtures.api import (
    get_workflow_status,
    submit_workflow,
    trigger_workflow,
)
from tests.integration.fixtures.diagnostics import inspect_database
from tests.integration.fixtures.infrastructure import InfrastructureConfig
from tests.integration.fixtures.lifecycle import running_application_services
from tests.integration.fixtures.polling import wait_for_workflow_status

pytestmark = pytest.mark.integration


def test_failed_workflow_reports_failed_node_and_withholds_results(
    api_client: TestClient,
    integration_infrastructure: InfrastructureConfig,
) -> None:
    with running_application_services(
        integration_infrastructure,
        environment_overrides={
            "MOCK_EXTERNAL_SERVICE_FORCE_FAIL": "true",
            "MOCK_EXTERNAL_SERVICE_FAILURE_MESSAGE": "integration failure",
            "WORKFLOW_TASK_MAX_ATTEMPTS": "1",
        },
    ) as (orchestrator, worker):
        execution_id = submit_workflow(
            api_client,
            [
                {
                    "id": "failure",
                    "handler": "call_external_service",
                    "dependencies": [],
                    "config": {"url": "https://failure.example"},
                }
            ],
            name_prefix="failed-api-workflow",
        )
        trigger_workflow(api_client, execution_id)

        failed = wait_for_workflow_status(
            lambda: get_workflow_status(api_client, execution_id),
            str(execution_id),
            "FAILED",
            diagnostics=lambda: f"{orchestrator.output()}\n{worker.output()}",
        )
        assert failed["status"] == "FAILED"
        nodes = failed["nodes"]
        assert isinstance(nodes, list)
        assert len(nodes) == 1
        assert nodes[0]["node_id"] == "failure"
        assert nodes[0]["status"] == "FAILED"
        assert nodes[0]["started_at"] is not None
        assert nodes[0]["completed_at"] is not None

        result_response = api_client.get(f"/workflows/{execution_id}/results")
        assert result_response.status_code == 200
        results = result_response.json()
        assert results["status"] == "FAILED"
        assert results["message"] == ("Workflow execution failed. Final results are not available.")
        assert results["results"] is None

        persisted = inspect_database(integration_infrastructure, execution_id)
        assert persisted.workflow_execution is not None
        assert persisted.workflow_execution[1] == "failed"
        assert persisted.node_executions[0][1] == "failed"


def test_failed_execution_cannot_be_triggered_again_or_create_duplicate_work(
    api_client: TestClient,
    integration_infrastructure: InfrastructureConfig,
) -> None:
    with running_application_services(
        integration_infrastructure,
        environment_overrides={
            "MOCK_EXTERNAL_SERVICE_FORCE_FAIL": "true",
            "WORKFLOW_TASK_MAX_ATTEMPTS": "1",
        },
    ) as (orchestrator, worker):
        execution_id = submit_workflow(
            api_client,
            [
                {
                    "id": "failure",
                    "handler": "call_external_service",
                    "dependencies": [],
                    "config": {"url": "https://failure-once.example"},
                }
            ],
            name_prefix="failed-repeat-api-workflow",
        )
        trigger_workflow(api_client, execution_id)
        wait_for_workflow_status(
            lambda: get_workflow_status(api_client, execution_id),
            str(execution_id),
            "FAILED",
            diagnostics=lambda: f"{orchestrator.output()}\n{worker.output()}",
        )
        before_retry = inspect_database(integration_infrastructure, execution_id)

        repeated = api_client.post(f"/workflow/trigger/{execution_id}")

        assert repeated.status_code == 422
        assert repeated.json()["error_code"] == "workflow_execution_not_triggerable"
        assert inspect_database(integration_infrastructure, execution_id) == before_retry
