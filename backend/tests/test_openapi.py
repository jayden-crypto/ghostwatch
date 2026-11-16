"""The generated OpenAPI document covers the contract and documents errors in the contract's envelope."""

import re
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import REPO_ROOT
from app.main import create_app

CONTRACT = (REPO_ROOT / "contract" / "API_CONTRACT.md").read_text()
# Contract endpoints that are P1 and not built yet. This set may only shrink.
NOT_IMPLEMENTED: set[tuple[str, str]] = set()
ROW = re.compile(r"^\| (GET|POST|PATCH|PUT|DELETE)( 🔑)? \| `(/[^`?]*)", re.MULTILINE)


def contract_endpoints() -> dict[tuple[str, str], bool]:
    """(method, path) -> whether the contract marks it 🔑, read from the contract's endpoint tables."""
    endpoints: dict[tuple[str, str], bool] = {}
    for method, key, path in ROW.findall(CONTRACT):
        # The first row for an endpoint is its definition; a later mention (the worker's use of
        # GET /replays, "works with or without the key") does not change it.
        endpoints.setdefault((method, path), bool(key))
    return endpoints


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    return create_app().openapi()


def operations(spec: dict[str, Any]) -> Iterator[tuple[str, str, dict[str, Any]]]:
    for path, methods in spec["paths"].items():
        for method, operation in methods.items():
            yield method.upper(), path.removeprefix("/api/v1"), operation


def test_the_contract_tables_were_parsed() -> None:
    endpoints = contract_endpoints()
    assert len(endpoints) == 22
    assert endpoints[("POST", "/executions/{execution_id}/events")] is True
    assert endpoints[("GET", "/stats/timeseries")] is False
    assert sum(endpoints.values()) == 4  # agents, executions, events, replay claim


def test_every_contract_endpoint_is_implemented_or_listed_as_not_implemented(spec: dict[str, Any]) -> None:
    implemented = {(method, path) for method, path, _ in operations(spec)}
    contract = set(contract_endpoints())
    assert implemented | NOT_IMPLEMENTED == contract
    assert not implemented & NOT_IMPLEMENTED, "implemented endpoints must be removed from NOT_IMPLEMENTED"
    assert all(path.startswith("/api/v1/") for path in spec["paths"])


def test_every_operation_is_described(spec: dict[str, Any]) -> None:
    tags = {tag["name"] for tag in spec["tags"]}
    for method, path, operation in operations(spec):
        where = f"{method} {path}"
        assert operation.get("summary"), where
        assert len(operation.get("description", "")) > 30, where
        assert operation.get("tags") and set(operation["tags"]) <= tags, where
        success = [response for status, response in operation["responses"].items() if status.startswith("2")]
        assert success and all("$ref" in r["content"]["application/json"]["schema"] for r in success), where


def test_errors_are_documented_in_the_contract_envelope(spec: dict[str, Any]) -> None:
    assert "HTTPValidationError" not in spec["components"]["schemas"]
    assert "ValidationError" not in spec["components"]["schemas"]
    envelope = {"$ref": "#/components/schemas/ErrorEnvelope"}
    for method, path, operation in operations(spec):
        errors = {status: r for status, r in operation["responses"].items() if status[0] in "45"}
        assert "500" in errors, f"{method} {path}"
        for status, response in errors.items():
            assert response["content"]["application/json"]["schema"] == envelope, f"{method} {path} {status}"
            assert response["description"].startswith("`"), f"{method} {path} {status}: name the error code"
        has_parameters = bool(operation.get("parameters")) or "requestBody" in operation
        path_only = (
            all(p["in"] == "path" for p in operation.get("parameters", [])) and "requestBody" not in operation
        )
        if has_parameters and not path_only:
            assert "422" in errors, f"{method} {path} takes input but documents no validation error"
        if "{" in path:
            assert "404" in errors, f"{method} {path} takes an id but documents no 404"


def test_ingestion_endpoints_require_the_key_and_read_endpoints_do_not(spec: dict[str, Any]) -> None:
    assert spec["components"]["securitySchemes"] == {
        "IngestionKey": {
            "type": "http",
            "scheme": "bearer",
            "description": "The ingestion key (`GHOSTWATCH_API_KEY`). Required by the endpoints an SDK writes to.",
        }
    }
    marked = contract_endpoints()
    for method, path, operation in operations(spec):
        secured = operation.get("security") == [{"IngestionKey": []}]
        assert secured == marked[(method, path)], f"{method} {path}"
        assert ("401" in operation["responses"]) == secured, f"{method} {path}"


def test_docs_pages_are_served() -> None:
    client = TestClient(create_app())
    assert client.get("/docs").status_code == 200
    document = client.get("/openapi.json").json()
    assert document["info"]["title"] == "Ghostwatch API"
    assert "contract/API_CONTRACT.md" in document["info"]["description"]


def test_the_api_key_must_not_be_empty() -> None:
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None, ghostwatch_api_key="")


def test_docs_api_md_covers_every_endpoint(spec: dict[str, Any]) -> None:
    """docs/API.md is generated by scripts/api_docs.py; it must not fall behind the routes."""
    document = (REPO_ROOT / "docs" / "API.md").read_text()
    for method, path, _ in operations(spec):
        assert f"### `{method} {path}" in document, f"docs/API.md has no section for {method} {path}"
    not_implemented = document.split("## Not implemented")[1]
    for method, path in NOT_IMPLEMENTED:
        assert path in not_implemented and method in not_implemented, (
            f"{method} {path} is not listed as not implemented"
        )
    assert "{{" not in document
