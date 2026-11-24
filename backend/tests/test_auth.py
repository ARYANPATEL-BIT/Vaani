"""Tests for Google sign-in (vaani/auth.py): the cookie, the routes, startup.

No test talks to Google. The app takes a stand-in verifier (`verify_google=`),
a plain function that returns the claims a real Google ID token would carry,
or raises the way the real verifier does: ValueError for a bad token,
GoogleUnavailable when Google's certificates cannot be fetched.
"""

import time

import pytest
from fastapi.testclient import TestClient
from google.auth import exceptions as google_exceptions

import vaani.auth as auth_mod
from vaani.app import create_app
from vaani.auth import (
    COOKIE_NAME,
    AuthConfigError,
    GoogleUnavailable,
    read_cookie,
    sign_cookie,
    verify_google,
)
from vaani.config import AuthSettings, Settings

SECRET = "s" * 32  # test-only; long enough for the 32-character minimum
ORIGIN = "http://localhost:5173"
EMAIL = "aryan@example.com"
HOUR = 3600


def auth_settings(**overrides) -> AuthSettings:
    """An enabled [auth] section with every required value filled in."""
    values = dict(
        enabled=True,
        google_client_id="test-client-id",
        session_secret=SECRET,
        allowed_emails=[EMAIL],
        allowed_origins=[ORIGIN],
    )
    values.update(overrides)
    return AuthSettings(**values)


def claims(**overrides) -> dict:
    """What verify_oauth2_token returns for a good Google ID token."""
    values = dict(sub="1234567890", email=EMAIL, email_verified=True, name="Aryan")
    values.update(overrides)
    return values


def fake_verifier(result):
    """A verify_google stand-in: returns `result`, or raises it if it is one."""

    def verify(credential: str, cfg: AuthSettings) -> dict:
        if isinstance(result, Exception):
            raise result
        return result

    return verify


def make_client(result=None, **auth_overrides) -> TestClient:
    settings = Settings(auth=auth_settings(**auth_overrides))
    app = create_app(settings, verify_google=fake_verifier(result or claims()))
    return TestClient(app)


def sign_in(client: TestClient, origin: str = ORIGIN):
    return client.post(
        "/auth/google",
        json={"credential": "a-google-id-token"},
        headers={"origin": origin},
    )


# --- the cookie -------------------------------------------------------------


def test_valid_cookie_is_accepted():
    value = sign_cookie("sub-1", EMAIL, "Aryan", time.time() + HOUR, SECRET)
    assert read_cookie(value, auth_settings()) == {"email": EMAIL, "name": "Aryan"}


def test_name_with_a_bar_and_non_ascii_survives():
    # A Devanagari name plus a "|", the cookie's own field separator.
    name = "आर्यन | P"
    value = sign_cookie("sub-1", EMAIL, name, time.time() + HOUR, SECRET)
    assert value.isascii()  # cookie values must be ASCII
    assert read_cookie(value, auth_settings())["name"] == name


def test_tampered_cookie_is_rejected():
    value = sign_cookie("sub-1", EMAIL, "Aryan", time.time() + HOUR, SECRET)
    payload, signature = value.split(".")
    # Change one character of the signed part, keep the old signature.
    flipped = ("A" if payload[0] != "A" else "B") + payload[1:]
    assert read_cookie(f"{flipped}.{signature}", auth_settings()) is None


def test_expired_cookie_is_rejected():
    value = sign_cookie("sub-1", EMAIL, "Aryan", time.time() - 1, SECRET)
    assert read_cookie(value, auth_settings()) is None


def test_cookie_signed_with_another_secret_is_rejected():
    value = sign_cookie("sub-1", EMAIL, "Aryan", time.time() + HOUR, "x" * 32)
    assert read_cookie(value, auth_settings()) is None


@pytest.mark.parametrize(
    "value", [None, "", "garbage", "a.b.c", "!!!.deadbeef", "éé.é"]
)
def test_missing_or_malformed_cookie_is_rejected(value):
    assert read_cookie(value, auth_settings()) is None


def test_cookie_of_an_email_removed_from_the_allowlist_is_rejected():
    value = sign_cookie("sub-1", EMAIL, "Aryan", time.time() + HOUR, SECRET)
    assert (
        read_cookie(value, auth_settings(allowed_emails=["other@example.com"])) is None
    )


# --- POST /auth/google --------------------------------------------------------


def test_sign_in_sets_an_httponly_lax_cookie_and_returns_the_user():
    client = make_client()
    response = sign_in(client)
    assert response.status_code == 200
    assert response.json() == {"email": EMAIL, "name": "Aryan"}
    header = response.headers["set-cookie"].lower()
    assert header.startswith(f"{COOKIE_NAME}=")
    assert "httponly" in header and "samesite=lax" in header
    assert "secure" not in header  # secure_cookie defaults to false (dev, http)
    assert f"max-age={7 * 24 * HOUR}" in header


def test_secure_cookie_setting_adds_secure():
    response = sign_in(make_client(secure_cookie=True))
    assert "secure" in response.headers["set-cookie"].lower()


def test_allowlist_match_ignores_case():
    response = sign_in(make_client(claims(email="Aryan@Example.COM")))
    assert response.status_code == 200
    assert response.json()["email"] == EMAIL


def test_email_not_in_allowlist_is_rejected():
    response = sign_in(make_client(claims(email="stranger@example.com")))
    assert response.status_code == 403
    assert response.json()["code"] == "AUTH_NOT_ALLOWED"
    assert "set-cookie" not in response.headers


def test_unverified_email_is_rejected():
    response = sign_in(make_client(claims(email_verified=False)))
    assert response.status_code == 403
    assert response.json()["code"] == "AUTH_EMAIL_UNVERIFIED"
    assert "set-cookie" not in response.headers


def test_invalid_google_token_is_rejected():
    response = sign_in(make_client(ValueError("Token expired")))
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_INVALID_TOKEN"


def test_google_unreachable_is_a_503():
    response = sign_in(make_client(GoogleUnavailable("cannot fetch certs")))
    assert response.status_code == 503
    assert response.json()["code"] == "AUTH_UNAVAILABLE"


def test_sign_in_from_another_origin_is_rejected():
    response = sign_in(make_client(), origin="https://evil.example")
    assert response.status_code == 403
    assert response.json()["code"] == "AUTH_BAD_ORIGIN"


# --- allow_all_emails ---------------------------------------------------------


def test_allow_all_accepts_an_unlisted_verified_email():
    client = make_client(claims(email="stranger@example.com"), allow_all_emails=True)
    response = sign_in(client)
    assert response.status_code == 200
    assert response.json()["email"] == "stranger@example.com"
    # The cookie path too: read_cookie must not re-check the allowlist.
    assert client.get("/auth/me").json()["email"] == "stranger@example.com"


def test_allow_all_still_rejects_an_unverified_email():
    unverified = claims(email="stranger@example.com", email_verified=False)
    response = sign_in(make_client(unverified, allow_all_emails=True))
    assert response.status_code == 403
    assert response.json()["code"] == "AUTH_EMAIL_UNVERIFIED"
    assert "set-cookie" not in response.headers


def test_allow_all_is_off_by_default():
    # Off, the allowlist tests above (not in allowlist, removed from it) hold.
    assert AuthSettings().allow_all_emails is False


def test_allow_all_permits_an_empty_allowlist_and_warns_once(caplog):
    create_app(Settings(auth=auth_settings(allowed_emails=[], allow_all_emails=True)))
    warnings = [
        r.message for r in caplog.records if r.name == "vaani.auth" and r.levelname == "WARNING"
    ]
    assert warnings == ["auth: all verified google accounts are allowed"]


# --- GET /auth/me, POST /auth/logout ----------------------------------------


def test_me_after_sign_in_returns_the_user():
    client = make_client()
    sign_in(client)  # TestClient keeps the cookie, like a browser
    response = client.get("/auth/me")
    assert response.status_code == 200
    assert response.json() == {"email": EMAIL, "name": "Aryan"}


def test_me_without_a_cookie_is_401():
    response = make_client().get("/auth/me")
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


def test_logout_clears_the_cookie():
    client = make_client()
    sign_in(client)
    response = client.post("/auth/logout", headers={"origin": ORIGIN})
    assert response.status_code == 204
    assert "max-age=0" in response.headers["set-cookie"].lower()
    assert client.get("/auth/me").status_code == 401


# --- auth disabled ------------------------------------------------------------


def test_disabled_me_answers_with_no_user():
    client = TestClient(create_app(Settings(auth=AuthSettings(enabled=False))))
    response = client.get("/auth/me")
    assert response.status_code == 200
    assert response.json() == {"email": None, "name": None}


def test_disabled_sign_in_route_is_not_found():
    client = TestClient(create_app(Settings(auth=AuthSettings(enabled=False))))
    assert sign_in(client).status_code == 404


# --- startup ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "named"),
    [
        ({"session_secret": None}, "VAANI_AUTH__SESSION_SECRET"),
        ({"session_secret": "short"}, "VAANI_AUTH__SESSION_SECRET"),
        ({"google_client_id": None}, "VAANI_AUTH__GOOGLE_CLIENT_ID"),
        ({"allowed_emails": []}, "VAANI_AUTH__ALLOWED_EMAILS"),
        ({"allowed_origins": []}, "VAANI_AUTH__ALLOWED_ORIGINS"),
    ],
)
def test_startup_refuses_incomplete_auth_settings(overrides, named):
    with pytest.raises(AuthConfigError) as caught:
        create_app(Settings(auth=auth_settings(**overrides)))
    assert named in str(caught.value)
    assert SECRET not in str(caught.value)  # names the variable, never a value


# --- verify_google: how Google's errors are mapped (no network) --------------


def test_verify_google_maps_a_transport_error_to_unavailable(monkeypatch):
    def unreachable(*args, **kwargs):
        raise google_exceptions.TransportError("no route to host")

    monkeypatch.setattr(auth_mod.id_token, "verify_oauth2_token", unreachable)
    with pytest.raises(GoogleUnavailable):
        verify_google("token", auth_settings())


def test_verify_google_maps_a_wrong_issuer_to_value_error(monkeypatch):
    def wrong_issuer(*args, **kwargs):
        raise google_exceptions.GoogleAuthError("Wrong issuer")

    monkeypatch.setattr(auth_mod.id_token, "verify_oauth2_token", wrong_issuer)
    with pytest.raises(ValueError):
        verify_google("token", auth_settings())


def test_verify_google_checks_our_client_id_with_skew_and_timeout(monkeypatch):
    seen = {}

    def record(token, request, audience, clock_skew_in_seconds):
        seen.update(audience=audience, skew=clock_skew_in_seconds)
        seen["timeout"] = request.keywords["timeout"]  # functools.partial
        return claims()

    monkeypatch.setattr(auth_mod.id_token, "verify_oauth2_token", record)
    cfg = auth_settings(clock_skew_s=10, google_timeout_s=5.0)
    assert verify_google("token", cfg) == claims()
    assert seen == {"audience": "test-client-id", "skew": 10, "timeout": 5.0}
