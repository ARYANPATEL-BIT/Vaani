"""Google sign-in, the session cookie, and the /ws/session handshake check.

How a user gets in:
  1. The browser shows Google's sign-in button. Google hands it an ID token:
     a JSON Web Token (JWT) signed by Google that says who the user is.
  2. The browser POSTs it to /auth/google. We check Google's signature and
     that the token was issued for OUR client ID (verify_google), then that
     the email is verified and on the allowlist.
  3. We answer with our OWN cookie, vaani_session: "sub|email|expiry|name",
     base64url-encoded and signed with HMAC-SHA256 under [auth]
     session_secret. HttpOnly, so page JavaScript can never read it.
  4. The browser sends that cookie by itself with every later request,
     including the WebSocket upgrade, where handshake_refusal checks it
     before the gateway accepts the socket (protocol v0.11).

No sessions table: the cookie carries everything and the signature proves we
wrote it. read_cookie re-checks the allowlist every time, so removing an
email locks that user out at the next request (after a restart, since
settings are read once).

This is the only module that imports google-auth (CLAUDE.md).
"""

import asyncio
import base64
import functools
import hashlib
import hmac
import logging
import time

from fastapi import APIRouter, HTTPException, Request, WebSocket
from fastapi.responses import JSONResponse, Response
from google.auth import exceptions as google_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from pydantic import BaseModel

from vaani.config import AuthSettings
from vaani.protocol import ErrorCode, error

log = logging.getLogger("vaani.auth")

COOKIE_NAME = "vaani_session"
# HMAC-SHA256 is only as strong as its key: refuse a short secret at startup.
MIN_SECRET_CHARS = 32

router = APIRouter(prefix="/auth")


class AuthConfigError(Exception):
    """[auth] is enabled but a required value is missing; the server stops."""


class GoogleUnavailable(Exception):
    """Google's certificates could not be fetched: we cannot judge the token."""


def check_settings(cfg: AuthSettings) -> None:
    """Raise AuthConfigError naming the first missing variable, never a value."""
    secret = cfg.session_secret.get_secret_value() if cfg.session_secret else ""
    problems = [
        (not cfg.google_client_id, "VAANI_AUTH__GOOGLE_CLIENT_ID is not set"),
        (not secret, "VAANI_AUTH__SESSION_SECRET is not set"),
        (
            0 < len(secret) < MIN_SECRET_CHARS,
            f"VAANI_AUTH__SESSION_SECRET is shorter than {MIN_SECRET_CHARS} characters",
        ),
        (not cfg.allowed_emails, "VAANI_AUTH__ALLOWED_EMAILS is empty"),
        (not cfg.allowed_origins, "VAANI_AUTH__ALLOWED_ORIGINS is empty"),
    ]
    for failed, message in problems:
        if failed:
            raise AuthConfigError(
                f"[auth] enabled is true but {message} (env or backend/.env). "
                "Set it, or set VAANI_AUTH__ENABLED=false to run without sign-in."
            )


# --- the cookie -------------------------------------------------------------


def _signature(payload: str, secret: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def sign_cookie(sub: str, email: str, name: str, expires_at: float, secret: str) -> str:
    """The cookie value: "<base64url payload>.<hex HMAC of that payload>".

    base64url because the name can be any Unicode and a cookie must be ASCII.
    The signature covers the encoded text, exactly what read_cookie gets back.
    """
    raw = f"{sub}|{email}|{int(expires_at)}|{name}"
    payload = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
    return f"{payload}.{_signature(payload, secret)}"


def read_cookie(value: str | None, cfg: AuthSettings) -> dict | None:
    """{email, name} if `value` is our unexpired, untampered cookie for an
    allowed email; otherwise None. Any malformed value is simply None."""
    if not value or value.count(".") != 1:
        return None
    payload, signature = value.split(".")
    expected = _signature(payload, cfg.session_secret.get_secret_value())
    # compare_digest takes the same time whether the first or the last
    # character differs, so response timing cannot leak the right signature
    # one character at a time. A plain == stops at the first difference.
    # Bytes, not str: compare_digest raises on a non-ASCII str, and this
    # value comes from the client, so it can hold anything.
    if not hmac.compare_digest(signature.encode(), expected.encode()):
        return None
    # Only now, with the signature proven ours, is the payload parsed.
    padded = payload + "=" * (-len(payload) % 4)
    # maxsplit=3: the name is last, so a "|" inside it stays in the name.
    sub, email, expires_at, name = (
        base64.urlsafe_b64decode(padded).decode().split("|", 3)
    )
    if int(expires_at) <= time.time() or email not in cfg.allowed_emails:
        return None
    return {"email": email, "name": name}


def origin_allowed(origin: str | None, cfg: AuthSettings) -> bool:
    """Exact match only: "http://localhost:5173" is not "http://127.0.0.1:5173"."""
    return origin in cfg.allowed_origins


def handshake_refusal(websocket: WebSocket, cfg: AuthSettings) -> str | None:
    """Why /ws/session must refuse this upgrade, or None to accept it.

    Plain local work (a set lookup and one HMAC), no network: this runs on
    every session start. The Origin check stops cross-site WebSocket
    hijacking: browsers attach our cookie to a WebSocket opened by ANY site,
    but they always send that site's real Origin, which a page cannot forge.
    """
    if not cfg.enabled:
        return None
    if not origin_allowed(websocket.headers.get("origin"), cfg):
        return "origin not allowed"
    if read_cookie(websocket.cookies.get(COOKIE_NAME), cfg) is None:
        return "no valid session cookie"
    return None


# --- Google -------------------------------------------------------------------


def verify_google(credential: str, cfg: AuthSettings) -> dict:
    """Check a Google ID token; return its claims (sub, email, name, ...).

    BLOCKING: google-auth downloads Google's public certificates with
    `requests` on every call (it does not cache them). The route runs this in
    a worker thread so the event loop, and every live audio session on it,
    never waits on Google. The download's timeout is ours (google_timeout_s);
    google-auth's own default is 120 s. A thread cannot be cancelled, so that
    timeout is what bounds it.

    Raises GoogleUnavailable if Google cannot be reached, ValueError if the
    token is bad (signature, audience, issuer or expiry).
    """
    request = functools.partial(google_requests.Request(), timeout=cfg.google_timeout_s)
    try:
        return id_token.verify_oauth2_token(
            credential,
            request,
            audience=cfg.google_client_id,
            clock_skew_in_seconds=cfg.clock_skew_s,
        )
    except google_exceptions.TransportError as exc:  # before its parent class
        raise GoogleUnavailable(str(exc)) from exc
    except google_exceptions.GoogleAuthError as exc:  # e.g. wrong issuer
        raise ValueError(str(exc)) from exc


# --- routes -------------------------------------------------------------------


class GoogleSignIn(BaseModel):
    credential: str  # the ID token from Google's button callback


def _fail(status: int, code: ErrorCode, message: str) -> JSONResponse:
    return JSONResponse(error(code, message), status_code=status)


@router.post("/google")
async def google_sign_in(body: GoogleSignIn, request: Request) -> Response:
    cfg: AuthSettings = request.app.state.settings.auth
    if not cfg.enabled:
        raise HTTPException(status_code=404)
    # A POST from a page on another site would still carry its own Origin;
    # refusing it means no other site can sign a visitor in or out.
    if not origin_allowed(request.headers.get("origin"), cfg):
        return _fail(403, ErrorCode.AUTH_BAD_ORIGIN, "origin not allowed")
    verify = request.app.state.verify_google
    try:
        # to_thread: the default executor, not the ASR / TTS thread pools.
        claims = await asyncio.to_thread(verify, body.credential, cfg)
    except GoogleUnavailable:
        log.warning("sign-in: Google certificates unreachable")
        return _fail(503, ErrorCode.AUTH_UNAVAILABLE, "cannot reach Google, try again")
    except ValueError:
        return _fail(401, ErrorCode.AUTH_INVALID_TOKEN, "Google token rejected")
    if not claims.get("email_verified"):
        return _fail(403, ErrorCode.AUTH_EMAIL_UNVERIFIED, "email not verified")
    email = claims["email"].lower()
    if email not in cfg.allowed_emails:
        log.info("sign-in refused: account not on the allowlist")
        return _fail(403, ErrorCode.AUTH_NOT_ALLOWED, "this account is not allowed")
    name = claims.get("name") or email
    max_age = cfg.cookie_days * 24 * 3600
    value = sign_cookie(
        claims["sub"],
        email,
        name,
        time.time() + max_age,
        cfg.session_secret.get_secret_value(),
    )
    response = JSONResponse({"email": email, "name": name})
    response.set_cookie(
        COOKIE_NAME,
        value,
        max_age=max_age,
        path="/",
        httponly=True,  # page JavaScript cannot read it, so XSS cannot steal it
        samesite="lax",  # not sent on POSTs or sockets started by other sites
        secure=cfg.secure_cookie,
    )
    return response


@router.get("/me")
async def me(request: Request) -> Response:
    cfg: AuthSettings = request.app.state.settings.auth
    if not cfg.enabled:
        return JSONResponse({"email": None, "name": None})
    user = read_cookie(request.cookies.get(COOKIE_NAME), cfg)
    if user is None:
        return _fail(401, ErrorCode.AUTH_REQUIRED, "sign in first")
    return JSONResponse(user)


@router.post("/logout")
async def logout(request: Request) -> Response:
    cfg: AuthSettings = request.app.state.settings.auth
    if cfg.enabled and not origin_allowed(request.headers.get("origin"), cfg):
        return _fail(403, ErrorCode.AUTH_BAD_ORIGIN, "origin not allowed")
    response = Response(status_code=204)
    # Same name, path and flags as when it was set, or the browser keeps it.
    response.delete_cookie(
        COOKIE_NAME, path="/", httponly=True, samesite="lax", secure=cfg.secure_cookie
    )
    return response
