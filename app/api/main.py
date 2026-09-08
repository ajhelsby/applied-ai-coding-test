from collections.abc import Callable
from typing import Any, cast

from fastapi import FastAPI

from app.api.workflows import router as workflows_router
from app.db.session import close_database_connections

app = FastAPI(title="Workflow Engine API")
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
