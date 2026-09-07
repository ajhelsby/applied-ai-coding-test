"""Dependency providers for persistence abstractions."""

from collections.abc import AsyncIterator

from app.domain.repositories.unit_of_work import UnitOfWork
from app.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork


async def get_unit_of_work() -> AsyncIterator[UnitOfWork]:
    """Provide a unit-of-work dependency to application layers."""
    yield SqlAlchemyUnitOfWork()
