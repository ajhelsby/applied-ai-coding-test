import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI

from app.api.workflows import router as workflows_router
from app.db.session import close_database_connections


def _application_version() -> str:
    manifest_path = Path(__file__).resolve().parents[2] / ".release-please-manifest.json"
    with manifest_path.open(encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)

    version_value = manifest.get(".") if isinstance(manifest, dict) else None
    if not isinstance(version_value, str):
        raise RuntimeError(f"Invalid release-please manifest: {manifest_path}")
    return version_value


app = FastAPI(
    title="Workflow Engine API",
    version=_application_version(),
)
app.include_router(workflows_router)

route_get = cast(Callable[[str], Callable[[Callable[..., Any]], Callable[..., Any]]], app.get)
route_on_event = cast(
    Callable[[str], Callable[[Callable[..., Any]], Callable[..., Any]]],
    app.on_event,
)


@route_get("/")
def root() -> dict[str, str]:
    return {"status": "ok"}


@route_get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@route_on_event("shutdown")
async def shutdown_event() -> None:
    await close_database_connections()
