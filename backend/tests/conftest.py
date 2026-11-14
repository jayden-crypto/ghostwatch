"""Shared fixtures. The app under test always talks to the test database, never the dev one."""

import contextlib
import os
import socket
import threading
from collections.abc import Iterator
from pathlib import Path

DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://ghostwatch:ghostwatch@localhost:5432/ghostwatch_test"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
os.environ.setdefault("GHOSTWATCH_API_KEY", "test-ingest-key")

import ghostwatch as gw  # noqa: E402
import pytest  # noqa: E402
import uvicorn  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from ghostwatch.client import NullTransport  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.api.deps import get_session_factory  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import get_engine, get_session  # noqa: E402
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


def alembic_config() -> Config:
    return Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))


@pytest.fixture(scope="session")
def migrated_database(database_available: None) -> None:
    """Rebuild the test database from the Alembic migration, so tests run on the real schema."""
    engine = get_engine()
    if not (engine.url.database or "").endswith("_test"):
        pytest.exit(f"Refusing to reset {engine.url.database!r}: the test database name must end in '_test'.")
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    command.upgrade(alembic_config(), "head")


@pytest.fixture
def db_session(migrated_database: None) -> Iterator[Session]:
    """A session inside an outer transaction that is rolled back after the test.

    Commits made by application code only release a savepoint, so nothing outlives the test.
    """
    connection = get_engine().connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    # Server exceptions are not re-raised: tests assert on the 500 response a real client would get.
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def db_client(app: FastAPI, db_session: Session) -> TestClient:
    """A client whose requests use the test's rolled-back session."""
    app.dependency_overrides[get_session] = lambda: db_session
    # Background tasks (investigations) see the same uncommitted test data.
    app.dependency_overrides[get_session_factory] = lambda: lambda: contextlib.nullcontext(db_session)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def auth() -> dict[str, str]:
    """Headers for the ingestion endpoints."""
    return {"Authorization": f"Bearer {get_settings().ghostwatch_api_key}"}


@pytest.fixture
def live_api(migrated_database: None, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """The app served by uvicorn on a free port. It commits for real, so the tables are emptied after."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    monkeypatch.setenv("SWEEPER_INTERVAL_SECONDS", "0.1")
    get_settings.cache_clear()
    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        while not server.started:
            assert thread.is_alive(), "the test server failed to start"
            thread.join(0.01)
        yield f"http://127.0.0.1:{port}/api/v1"
    finally:
        gw._sdk.transport.close(timeout=1)
        gw._sdk.transport = NullTransport()
        gw._sdk.initialised = False
        gw._sdk.last_execution = None
        server.should_exit = True
        thread.join(10)
        get_settings.cache_clear()
        with get_engine().begin() as connection:
            connection.execute(
                text("TRUNCATE replays, investigations, anomalies, steps, events, executions, agents CASCADE")
            )
