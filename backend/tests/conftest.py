"""Shared fixtures. The app under test always talks to the test database, never the dev one."""

import os

DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://ghostwatch:ghostwatch@localhost:5432/ghostwatch_test"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
os.environ.setdefault("GHOSTWATCH_API_KEY", "test-ingest-key")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from app.db import get_engine  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture(scope="session")
def database_available() -> None:
    """Skip database tests locally when Postgres is down; in CI a missing database is a failure."""
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError as exc:
        message = f"Postgres is not reachable at {get_engine().url.render_as_string(hide_password=True)}"
        if os.environ.get("CI"):
            pytest.fail(f"{message}: {exc}")
        pytest.skip(f"{message} (run `docker compose up -d`)")


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    # Server exceptions are not re-raised: tests assert on the 500 response a real client would get.
    return TestClient(app, raise_server_exceptions=False)
