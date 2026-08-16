"""Shared fixtures.

Every test drives the application through its real HTTP surface via an in-process ASGI
transport, and every test uses a controllable clock — so nothing sleeps, and every assertion is
exactly reproducible.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from flowjack.app import create_app
from flowjack.auth import demo_token
from flowjack.clock import FakeClock
from flowjack.config import Settings
from flowjack.db import Database

AppFactory = Callable[..., TestClient]


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def make_client(clock: FakeClock) -> Iterator[AppFactory]:
    created: list[Database] = []

    def factory(**overrides: object) -> TestClient:
        resolved = replace(Settings(), **overrides)  # type: ignore[arg-type]
        database = Database(resolved, clock)
        created.append(database)
        app = create_app(settings=resolved, clock=clock, database=database)
        return TestClient(app, base_url="http://flowjack.test")

    yield factory
    for database in created:
        database.close()


@pytest.fixture
def client(make_client: AppFactory) -> Iterator[TestClient]:
    with make_client() as instance:
        yield instance


def auth(patron_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {demo_token(patron_id)}"}
