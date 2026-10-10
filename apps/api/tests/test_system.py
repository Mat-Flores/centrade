from datetime import UTC, datetime, timedelta

import pytest
from centrade_api.errors import install_error_handlers
from centrade_api.main import app
from fastapi import FastAPI
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
