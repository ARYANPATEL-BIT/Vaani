"""Tests for the GET /health endpoint.

Verifies the endpoint answers correctly AND that it never leaks configuration
or secrets — the second property is a project constraint, not a nicety.
"""

from fastapi.testclient import TestClient

from vaani import __version__
from vaani.app import create_app


def test_health_returns_status_and_version() -> None:
    """/health responds 200 with exactly {status, version}."""
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_health_body_has_only_two_keys() -> None:
    """The response shape is locked to two keys so config cannot slip in."""
    client = TestClient(create_app())

    body = client.get("/health").json()

    assert set(body.keys()) == {"status", "version"}


def test_health_does_not_leak_a_secret(monkeypatch) -> None:
    """Even with a secret set in the environment, it must not appear anywhere
    in the /health response."""
    monkeypatch.setenv("VAANI_SECRET_KEY", "super-secret-value")
    # Rebuild the app so any settings read happens with the env var present.
    client = TestClient(create_app())

    raw = client.get("/health").text

    assert "super-secret-value" not in raw
