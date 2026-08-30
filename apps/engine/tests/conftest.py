"""Shared fixtures.

These tests run against the live database rather than fixtures, deliberately.
The properties worth protecting here are not "does this function return what I
typed into a mock" — they are "do the numbers in the database still mean what we
say they mean". A de-vig that stops summing to one, a ladder that stops being
monotone, a scoring timeline that stops reconciling to the final score: each of
those was a real defect found by hand, and each is one query away from being
found automatically.

Skips rather than fails when a table is empty, so a fresh checkout without an
ingest does not report a wall of red for data it was never given.
"""

import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://youredge:youredge_dev@localhost:5432/youredge",
)


# Function-scoped on purpose. A session-scoped async fixture binds its
# connection to the event loop that created it, and pytest-asyncio gives each
# test its own loop by default -- so a shared connection raises InterfaceError
# on the second test rather than being reused. Reconnecting per test costs
# milliseconds against queries that take longer than that anyway.
@pytest_asyncio.fixture
async def conn():
    engine = create_async_engine(DB_URL)
    try:
        async with engine.connect() as c:
            yield c
    finally:
        await engine.dispose()


async def count(conn, sql: str, **params) -> int:
    return (await conn.execute(text(sql), params)).scalar() or 0


async def require(conn, table: str) -> None:
    if await count(conn, f"SELECT count(*) FROM {table}") == 0:
        pytest.skip(f"{table} is empty; nothing to check")
