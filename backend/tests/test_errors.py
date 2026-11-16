"""Every non-2xx response uses the contract's envelope: {"error": {code, message, details}}."""

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from app.api.deps import require_api_key
from app.config import get_settings
from app.errors import ApiError

ORIGIN = "http://localhost:3000"


class Widget(BaseModel):
    name: str
    size: int


def assert_envelope(body: dict, code: str) -> dict:
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    return body["error"]


def test_unknown_route_is_not_found(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    error = assert_envelope(response.json(), "not_found")
    assert error["details"] is None


def test_wrong_method_uses_the_envelope(client: TestClient) -> None:
    response = client.delete("/api/v1/health")
    assert response.status_code == 405
    assert_envelope(response.json(), "bad_request")
    assert "GET" in response.headers["allow"]


def test_request_validation_lists_each_problem(app: FastAPI, client: TestClient) -> None:
    @app.post("/api/v1/_widgets")
    def create_widget(widget: Widget) -> Widget:
        return widget

    response = client.post("/api/v1/_widgets", json={"size": "big"})
    assert response.status_code == 422
    error = assert_envelope(response.json(), "validation_error")
    assert "detail" not in response.json()
    assert {tuple(item["loc"]) for item in error["details"]} == {("body", "name"), ("body", "size")}
    assert all(set(item) == {"loc", "msg"} and item["msg"] for item in error["details"])


def test_api_error_is_returned_as_given(app: FastAPI, client: TestClient) -> None:
    @app.get("/api/v1/_conflict")
    def conflict() -> None:
        raise ApiError(409, "execution_already_terminal", "Execution is already terminal.", {"seq": 7})

    response = client.get("/api/v1/_conflict")
    assert response.status_code == 409
    error = assert_envelope(response.json(), "execution_already_terminal")
    assert error["message"] == "Execution is already terminal."
    assert error["details"] == {"seq": 7}


def test_http_exception_maps_status_to_contract_code(app: FastAPI, client: TestClient) -> None:
    @app.get("/api/v1/_teapot/{status}")
    def raise_status(status: int) -> None:
        raise HTTPException(status_code=status, detail="nope")

    assert client.get("/api/v1/_teapot/400").json()["error"]["code"] == "bad_request"
    assert client.get("/api/v1/_teapot/409").json()["error"]["code"] == "conflict"
    assert client.get("/api/v1/_teapot/503").json()["error"]["code"] == "internal_error"


def test_unhandled_exception_is_a_500_without_leaking(app: FastAPI, client: TestClient) -> None:
    @app.get("/api/v1/_boom")
    def boom() -> None:
        raise RuntimeError("database password is hunter2")

    response = client.get("/api/v1/_boom", headers={"Origin": ORIGIN})
    assert response.status_code == 500
    error = assert_envelope(response.json(), "internal_error")
    assert error["details"] is None
    assert "hunter2" not in response.text
    assert "Traceback" not in response.text
    assert "RuntimeError" not in response.text
    # The browser can only read this body if the 500 carries CORS headers.
    assert response.headers["access-control-allow-origin"] == ORIGIN


def test_api_key_guard(app: FastAPI, client: TestClient) -> None:
    @app.post("/api/v1/_guarded", dependencies=[Depends(require_api_key)])
    def guarded() -> dict:
        return {"ok": True}

    key = get_settings().ghostwatch_api_key

    missing = client.post("/api/v1/_guarded")
    assert missing.status_code == 401
    assert_envelope(missing.json(), "unauthorized")

    for header in (f"Bearer {key}x", key, f"Basic {key}", "Bearer "):
        wrong = client.post("/api/v1/_guarded", headers={"Authorization": header})
        assert wrong.status_code == 401, header
        assert_envelope(wrong.json(), "unauthorized")

    ok = client.post("/api/v1/_guarded", headers={"Authorization": f"Bearer {key}"})
    assert ok.status_code == 200


def test_cors_allows_the_dashboard_origin_only(client: TestClient) -> None:
    allowed = client.get("/api/v1/health", headers={"Origin": ORIGIN})
    assert allowed.headers["access-control-allow-origin"] == ORIGIN

    preflight = client.options(
        "/api/v1/agents",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == ORIGIN

    other = client.get("/api/v1/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in other.headers
