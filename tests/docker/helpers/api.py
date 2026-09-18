"""HTTP helpers for exercising the deployed workflow API."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Self
from uuid import UUID, uuid4

import httpx

JsonObject = dict[str, object]


class DockerApiError(RuntimeError):
    """Raised when the deployed API returns an unexpected response."""


def _json_object(response: httpx.Response) -> JsonObject:
    payload: object = response.json()
    if not isinstance(payload, dict):
        raise DockerApiError(
            f"Expected a JSON object from {response.request.url}, got {payload!r}."
        )
    return {str(key): value for key, value in payload.items()}


class DockerApiClient:
    """Small HTTP client for the public workflow endpoints."""

    def __init__(self, base_url: str, *, timeout_seconds: float = 10.0) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout_seconds)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""

        self._client.close()

    def health(self) -> JsonObject:
        """Retrieve the API readiness response."""

        return self._request("GET", "/health", expected_status=200)

    def submit_workflow(
        self,
        nodes: Sequence[Mapping[str, object]],
        *,
        name: str | None = None,
        created_by: str = "docker-e2e-test",
    ) -> UUID:
        """Submit a workflow definition and return its execution identifier."""

        payload = {
            "name": name or f"docker-e2e-{uuid4()}",
            "created_by": created_by,
            "dag": {"nodes": [dict(node) for node in nodes]},
        }
        response = self._request("POST", "/workflow", json=payload, expected_status=201)
        execution_id = response.get("execution_id")
        if not isinstance(execution_id, str):
            raise DockerApiError(
                f"Submission response did not contain execution_id: {response!r}."
            )
        try:
            return UUID(execution_id)
        except ValueError as error:
            raise DockerApiError(
                f"Submission returned an invalid execution_id: {execution_id!r}."
            ) from error

    def trigger_workflow(
        self,
        execution_id: UUID,
        *,
        input_data: Mapping[str, object] | None = None,
    ) -> JsonObject:
        """Trigger an execution through the public API."""

        payload = {"input": dict(input_data or {})}
        return self._request(
            "POST",
            f"/workflow/trigger/{execution_id}",
            json=payload,
            expected_status=202,
        )

    def get_workflow_status(self, execution_id: UUID) -> JsonObject:
        """Retrieve persisted workflow execution status."""

        return self._request("GET", f"/workflows/{execution_id}", expected_status=200)

    def get_workflow_results(self, execution_id: UUID) -> JsonObject:
        """Retrieve persisted workflow execution results."""

        return self._request(
            "GET",
            f"/workflows/{execution_id}/results",
            expected_status=200,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        expected_status: int,
        json: JsonObject | None = None,
    ) -> JsonObject:
        response = self._client.request(method, path, json=json)
        if response.status_code != expected_status:
            raise DockerApiError(
                f"{method} {path} returned {response.status_code}, expected {expected_status}: "
                f"{response.text}"
            )
        return _json_object(response)
