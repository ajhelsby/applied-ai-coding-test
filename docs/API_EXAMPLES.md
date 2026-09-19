# API Examples

These examples use the local API exposed by Docker Compose at
`http://localhost:8000`. The same requests work against another API base URL.

## 1. Submit a workflow

Submission validates and persists the workflow, but does not start execution.

```bash
curl -X POST http://localhost:8000/workflow \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "document-enrichment",
    "dag": {
      "nodes": [
        {
          "id": "input",
          "handler": "input",
          "dependencies": [],
          "config": {}
        },
        {
          "id": "fetch",
          "handler": "call_external_service",
          "dependencies": ["input"],
          "config": {
            "url": "https://example.test/documents/{{ input.document_id }}"
          }
        },
        {
          "id": "result",
          "handler": "output",
          "dependencies": ["fetch"],
          "config": {}
        }
      ]
    }
  }'
```

The response contains the pending execution identifier:

```json
{
  "execution_id": "00000000-0000-0000-0000-000000000000",
  "name": "document-enrichment",
  "created_at": "2026-01-01T00:00:00Z"
}
```

Save the returned `execution_id` for the next requests.

## 2. Trigger the execution

Replace `EXECUTION_ID` with the identifier returned by submission.

```bash
curl -X POST "http://localhost:8000/workflow/trigger/EXECUTION_ID" \
  -H 'Content-Type: application/json' \
  -d '{
    "input": {
      "document_id": "example-document",
      "options": {
        "draft": true
      }
    }
  }'
```

The `202 Accepted` response acknowledges that asynchronous processing was
accepted; it does not mean that the workflow has completed.

```json
{
  "execution_id": "00000000-0000-0000-0000-000000000000",
  "status": "RUNNING"
}
```

## 3. Poll execution status

```bash
curl "http://localhost:8000/workflows/EXECUTION_ID"
```

The response includes the persisted workflow status and each node status.
Poll until the workflow is `completed` or `failed`.

```json
{
  "execution_id": "00000000-0000-0000-0000-000000000000",
  "workflow_id": "00000000-0000-0000-0000-000000000000",
  "status": "COMPLETED",
  "nodes": [
    {
      "node_id": "input",
      "status": "COMPLETED"
    },
    {
      "node_id": "fetch",
      "status": "COMPLETED"
    },
    {
      "node_id": "result",
      "status": "COMPLETED"
    }
  ]
}
```

## 4. Retrieve results

```bash
curl "http://localhost:8000/workflows/EXECUTION_ID/results"
```

Successful executions return persisted output for each node:

```json
{
  "execution_id": "00000000-0000-0000-0000-000000000000",
  "status": "COMPLETED",
  "message": null,
  "results": [
    {
      "node_id": "fetch",
      "status": "completed",
      "output_data": {
        "status": "mocked",
        "url": "https://example.test/documents/example-document",
        "input": {
          "document_id": "example-document",
          "options": {
            "draft": true
          }
        }
      }
    }
  ]
}
```

Pending or running executions return `results: null`. Failed executions also
return `results: null` and expose the persisted failure status.

## API documentation

When the application is running, FastAPI's interactive documentation is
available at [http://localhost:8000/docs](http://localhost:8000/docs).
