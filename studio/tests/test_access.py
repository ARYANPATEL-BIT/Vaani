"""Sign-in: every route but /studio/health needs the backend's session cookie."""

import pytest
from vaani.auth import COOKIE_NAME

from tests.conftest import (
    FakeCloner,
    FakeEncoder,
    FakeRecognizer,
    auth_settings,
    cookie_for,
)
from voice_studio.app import StudioConfigError, create_app

ROUTES = [
    ("get", "/studio/voice"),
    ("delete", "/studio/voice"),
    ("post", "/studio/challenge"),
    ("post", "/studio/enrol"),
    ("post", "/studio/generate"),
]


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_no_cookie_is_401(rig, method, path):
    rig.client.cookies.clear()
    response = getattr(rig.client, method)(path)
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_tampered_cookie_is_401(rig, method, path):
    value = cookie_for()
    rig.client.cookies.set(COOKIE_NAME, value[:-1] + ("0" if value[-1] != "0" else "1"))
    assert getattr(rig.client, method)(path).status_code == 401


def test_cookie_signed_with_another_secret_is_401(rig):
    from vaani.auth import sign_cookie

    rig.client.cookies.set(
        COOKIE_NAME, sign_cookie("s", "me@example.com", "Me", 9e9, "x" * 40)
    )
    assert rig.client.get("/studio/voice").status_code == 401


def test_email_not_allowed_is_401(rig):
    rig.client.cookies.set(COOKIE_NAME, cookie_for("someone@else.com"))
    assert rig.client.get("/studio/voice").status_code == 401


def test_post_from_another_origin_is_403(rig):
    response = rig.client.post(
        "/studio/challenge", headers={"origin": "https://evil.example"}
    )
    assert response.status_code == 403
    assert response.json()["code"] == "AUTH_BAD_ORIGIN"


def test_health_needs_no_cookie(rig):
    rig.client.cookies.clear()
    response = rig.client.get("/studio/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_signed_in_user_sees_consent_text_and_limits(rig):
    body = rig.client.get("/studio/voice").json()
    assert body["enrolled"] is False
    assert body["consent_text"] == rig.cfg.consent_text
    assert body["limits"]["max_script_chars"] == rig.cfg.max_script_chars


def test_studio_refuses_to_start_without_sign_in(tmp_path):
    from voice_studio.config import StudioSettings

    with pytest.raises(StudioConfigError):
        create_app(
            StudioSettings(data_dir=str(tmp_path)),
            auth_settings(enabled=False),
            FakeCloner(),
            FakeEncoder(),
            FakeRecognizer(),
        )
