"""Integration coverage for the generated workflow API documentation."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

_WORKFLOW_OPERATIONS = {
    ("/workflow", "post"): ("201", "WorkflowSubmissionResponse"),
    ("/workflow/trigger/{execution_id}", "post"): ("202", "WorkflowTriggerResponse"),
    ("/workflows/{execution_id}", "get"): ("200", "WorkflowExecutionStatusResponsePayload"),
    ("/workflows/{execution_id}/results", "get"): (
        "200",
        "WorkflowExecutionResultsResponsePayload",
    ),
}


def _schema_ref(schema: Mapping[str, object]) -> str:
    reference = schema.get("$ref")
    assert isinstance(reference, str)
    return reference.rsplit("/", maxsplit=1)[-1]


def _contains_schema_ref(schema: Mapping[str, object], expected: str) -> bool:
    if schema.get("$ref") == f"#/components/schemas/{expected}":
        return True
    alternatives = schema.get("anyOf")
    return isinstance(alternatives, list) and any(
        isinstance(alternative, Mapping) and _contains_schema_ref(alternative, expected)
        for alternative in alternatives
    )


def test_openapi_documents_all_workflow_operations_and_contracts(
    api_client: TestClient,
) -> None:
    response = api_client.get("/openapi.json")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    document = response.json()
    assert document["openapi"].startswith("3.")
    assert document["info"]["title"] == "Workflow Engine API"
    assert document["info"]["version"] == "0.0.8"

    paths = document["paths"]
    components = document["components"]["schemas"]
    for (path, method), (success_status, response_schema) in _WORKFLOW_OPERATIONS.items():
        assert path in paths
        operation = paths[path][method]
        assert operation["summary"]
        assert operation["description"]
        assert success_status in operation["responses"]
        success_response = operation["responses"][success_status]
        assert success_response["description"]
        assert _schema_ref(success_response["content"]["application/json"]["schema"]) == (
            response_schema
        )

    submission_operation = paths["/workflow"]["post"]
    submission_body = submission_operation["requestBody"]["content"]["application/json"]["schema"]
    assert _contains_schema_ref(submission_body, "WorkflowSubmissionRequest")
    assert {"422", "503"} <= set(submission_operation["responses"])

    trigger_operation = paths["/workflow/trigger/{execution_id}"]["post"]
    trigger_body = trigger_operation["requestBody"]["content"]["application/json"]["schema"]
    assert _contains_schema_ref(trigger_body, "WorkflowTriggerRequest")
    assert {"404", "422", "503"} <= set(trigger_operation["responses"])

    for path in ("/workflows/{execution_id}", "/workflows/{execution_id}/results"):
        operation = paths[path]["get"]
        assert "execution_id" in {parameter["name"] for parameter in operation["parameters"]}
        assert "404" in operation["responses"]
        parameter = next(
            parameter
            for parameter in operation["parameters"]
            if parameter["name"] == "execution_id"
        )
        assert parameter["description"]
        assert parameter["schema"]["format"] == "uuid"

    assert components["WorkflowSubmissionRequest"]["properties"]["name"]["description"]
    assert components["WorkflowDagRequest"]["properties"]["nodes"]["description"]
    assert components["WorkflowNode"]["properties"]["id"]["description"]
    assert components["WorkflowNode"]["properties"]["handler"]["description"]
    assert components["WorkflowNode"]["properties"]["dependencies"]["description"]
    assert components["WorkflowNode"]["properties"]["config"]["description"]
    assert components["WorkflowTriggerRequest"]["properties"]["input"]["description"]
    assert components["WorkflowTriggerRequest"]["properties"]["input"]["examples"]
    assert components["WorkflowExecutionStatusResponsePayload"]["properties"]["execution_id"][
        "description"
    ]
    assert components["WorkflowExecutionStatusResponsePayload"]["properties"]["nodes"][
        "description"
    ]
    assert components["WorkflowExecutionResultsResponsePayload"]["properties"]["results"][
        "description"
    ]


def test_openapi_exposes_examples_and_workflow_status_enums(
    api_client: TestClient,
) -> None:
    document = api_client.get("/openapi.json").json()
    schemas = document["components"]["schemas"]

    submission_schema = schemas["WorkflowSubmissionRequest"]
    assert submission_schema["properties"]["name"]["examples"] == ["document-enrichment"]
    node_schema = schemas["WorkflowNode"]
    assert node_schema["properties"]["config"]["examples"]
    assert "{{ input.value }}" in str(node_schema["properties"]["config"]["examples"])

    status_enums = [
        schema.get("enum")
        for schema in schemas.values()
        if isinstance(schema, Mapping) and "enum" in schema
    ]
    assert ["pending", "running", "completed", "failed"] in status_enums

    validation_schema = schemas["ValidationErrorResponse"]
    assert validation_schema["properties"]["error_code"]["examples"] == [
        "workflow_validation_failed"
    ]
    assert "errors" in validation_schema["properties"]


def test_swagger_ui_is_available(api_client: TestClient) -> None:
    response = api_client.get("/docs")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "swagger-ui" in response.text.lower()
