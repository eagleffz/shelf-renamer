import pytest
from app.config import Settings, get_settings
from app.main import app
from fastapi.testclient import TestClient
from pydantic import ValidationError


@pytest.fixture
def client(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(
        settings, "allowed_origins", "https://renamer.example,http://nas.local:8080"
    )
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "app_password", "test-password")
    with TestClient(app) as client:
        yield client


def test_allowed_origins_read_from_environment(monkeypatch):
    monkeypatch.setenv(
        "ALLOWED_ORIGINS",
        " https://RENAMER.example:443/, http://nas.local:8080, https://renamer.example ",
    )
    settings = Settings(_env_file=None)
    assert settings.trusted_origins() == [
        "https://renamer.example",
        "http://nas.local:8080",
    ]


@pytest.mark.parametrize(
    "value",
    [
        "*",
        "https://*.example",
        "null",
        "renamer.example",
        "ftp://renamer.example",
        "https://user:password@renamer.example",
        "https://renamer.example/path",
        "https://renamer.example?x=1",
        "https://renamer.example#fragment",
        "https://renamer.example:99999",
    ],
)
def test_invalid_allowlist_fails_configuration(value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, allowed_origins=value)


@pytest.mark.parametrize("origin", ["https://renamer.example", "http://nas.local:8080"])
def test_allowlisted_origin_can_login_through_proxy(client, origin):
    response = client.post(
        "/api/auth/login",
        headers={"Origin": origin},
        json={"password": "test-password"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "Origin" in response.headers["vary"]


def test_credentialed_cors_preflight(client):
    response = client.options(
        "/api/preview",
        headers={
            "Origin": "https://renamer.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://renamer.example"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "POST" in response.headers["access-control-allow-methods"]


@pytest.mark.parametrize(
    "origin",
    [
        "https://other.example",
        "https://renamer.example.evil",
        "https://sub.renamer.example",
        "http://renamer.example",
        "http://nas.local:8081",
        "null",
    ],
)
def test_unlisted_origins_stay_blocked(client, origin):
    response = client.post(
        "/api/auth/login",
        headers={"Origin": origin},
        json={"password": "test-password"},
    )
    assert response.status_code == 403
    assert "access-control-allow-origin" not in response.headers
    preflight = client.options(
        "/api/preview",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
    )
    assert preflight.status_code == 400
    assert "access-control-allow-origin" not in preflight.headers


def test_allowlist_does_not_bypass_authentication(client):
    response = client.post(
        "/api/preview",
        headers={"Origin": "https://renamer.example"},
        json={"template": "{title}", "items": []},
    )
    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "https://renamer.example"


def test_empty_allowlist_keeps_same_origin_and_cli_access(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "allowed_origins", "")
    for headers in [{"Origin": "http://testserver"}, {}]:
        assert (
            client.post(
                "/api/auth/login", headers=headers, json={"password": "test-password"}
            ).status_code
            == 200
        )
    assert (
        client.post(
            "/api/auth/login",
            headers={"Origin": "https://renamer.example"},
            json={"password": "test-password"},
        ).status_code
        == 403
    )


def test_debug_origin_still_works(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "debug", True)
    response = client.post(
        "/api/auth/login",
        headers={"Origin": "http://localhost:5173"},
        json={"password": "test-password"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
