import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_health() -> None:
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["content-type"] == "application/json"


def test_readiness_requires_database():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        assert client.get("/api/ready").status_code == 503


@pytest.mark.parametrize(
    "inventory,expected",
    [
        ({"models": [{"name": "test-model:latest"}]}, 200),
        ({"models": []}, 503),
        ({"models": None}, 503),
    ],
)
def test_readiness_checks_configured_model(client, monkeypatch, inventory, expected):
    config = client.app.state.settings
    config.llm_provider = "ollama"
    config.chat_model = "test-model"
    real_client = httpx.Client
    monkeypatch.setattr(
        "app.api.health.httpx.Client",
        lambda **kw: real_client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=inventory))
        ),
    )
    assert client.get("/api/ready").status_code == expected


def test_readiness_allows_search_only_mode(client):
    assert client.get("/api/ready").json()["answer_model"] == "disabled"
