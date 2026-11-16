from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import __version__
from app.config import Settings, get_settings
from app.db import get_session

HEALTH_KEYS = {"status", "version", "database", "llm_provider", "llm_configured", "llm_model"}


def unreachable_session() -> Iterator[Session]:
    engine = create_engine(
        "postgresql+psycopg://nobody:nobody@127.0.0.1:1/nothing", connect_args={"connect_timeout": 1}
    )
    with Session(engine) as session:
        yield session


def settings_with(**overrides: str) -> Settings:
    return Settings(_env_file=None, ghostwatch_api_key="k", **overrides)


def test_health_reports_database_ok(client: TestClient, database_available: None) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == HEALTH_KEYS
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["database"] == "ok"


def test_health_reports_database_error_without_failing(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[get_session] = unreachable_session
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == HEALTH_KEYS
    assert body["database"] == "error"


def test_health_rule_based_provider_needs_no_key(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[get_session] = unreachable_session
    app.dependency_overrides[get_settings] = lambda: settings_with(llm_provider="rule_based")
    body = client.get("/api/v1/health").json()
    assert body["llm_provider"] == "rule_based"
    assert body["llm_configured"] is True
    assert body["llm_model"] is None


def test_health_fable_without_key_is_not_configured(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[get_session] = unreachable_session
    app.dependency_overrides[get_settings] = lambda: settings_with(llm_provider="fable", anthropic_api_key="")
    body = client.get("/api/v1/health").json()
    assert body["llm_provider"] == "fable"
    assert body["llm_configured"] is False
    assert body["llm_model"] == "claude-fable-5-2"


def test_health_fable_with_key_is_configured(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[get_session] = unreachable_session
    app.dependency_overrides[get_settings] = lambda: settings_with(
        llm_provider="fable", anthropic_api_key="placeholder-not-a-real-key", llm_model="some-model"
    )
    body = client.get("/api/v1/health").json()
    assert body["llm_configured"] is True
    assert body["llm_model"] == "some-model"
