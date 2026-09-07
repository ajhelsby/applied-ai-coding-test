from collections.abc import Callable
from typing import Any, cast

from fastapi import FastAPI

from app.db import close_database_connections

app = FastAPI(title="Workflow Engine API")

route_get = cast(Callable[[str], Callable[[Callable[..., Any]], Callable[..., Any]]], app.get)


@route_get("/")
def root() -> dict[str, str]:
    return {"status": "ok"}


@route_get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await close_database_connections()
