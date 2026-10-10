from datetime import UTC, datetime, timedelta

import pytest
from centrade_api.errors import install_error_handlers
from centrade_api.main import app
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_reports_liveness_with_utc_timestamp(client: TestClient) -> None:
    response = client.get("/api/v1/system/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    ts = datetime.fromisoformat(body["ts"])
    assert ts.utcoffset() == timedelta(0)
    assert abs(datetime.now(UTC) - ts) < timedelta(seconds=5)


def test_health_does_not_report_unobserved_dependencies(client: TestClient) -> None:
    # I1 : l'API n'interroge ni Postgres ni Redis à M0, donc elle n'en dit rien.
    assert set(client.get("/api/v1/system/health").json()) == {"status", "ts"}


def test_unknown_route_returns_problem_json_404(client: TestClient) -> None:
    response = client.get("/api/v1/nope")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == 404
    assert body["title"] == "Not Found"
    assert body["instance"] == "/api/v1/nope"


def test_http_error_keeps_its_headers(client: TestClient) -> None:
    # Un 405 sans `Allow`, ou un 401 sans `WWW-Authenticate`, n'est pas exploitable.
    response = client.post("/api/v1/system/health")

    assert response.status_code == 405
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.headers["allow"] == "GET"


def test_unhandled_exception_returns_problem_json_500_without_detail() -> None:
    probe = FastAPI()
    install_error_handlers(probe)

    @probe.get("/boom")
    def boom() -> None:
        raise RuntimeError("TEST-SECRET-DO-NOT-USE")

    response = TestClient(probe, raise_server_exceptions=False).get("/boom")

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] == 500
    assert "TEST-SECRET-DO-NOT-USE" not in response.text


def test_non_standard_status_still_returns_problem_json() -> None:
    probe = FastAPI()
    install_error_handlers(probe)

    @probe.get("/closed")
    def closed() -> None:
        raise HTTPException(status_code=499)

    response = TestClient(probe).get("/closed")

    assert response.status_code == 499
    assert response.json()["status"] == 499


def test_openapi_is_served_under_the_api_prefix(client: TestClient) -> None:
    # Caddy ne route que /api/* vers l'API ; l'interface Swagger charge des scripts tiers (CSP).
    assert client.get("/api/v1/openapi.json").status_code == 200
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").status_code == 404


def test_validation_error_returns_problem_json_422() -> None:
    probe = FastAPI()
    install_error_handlers(probe)

    @probe.get("/n/{n}")
    def get_n(n: int) -> int:
        return n

    response = TestClient(probe).get("/n/abc")

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == 422
    assert body["errors"][0]["loc"] == ["path", "n"]
    assert "input" not in body["errors"][0]
