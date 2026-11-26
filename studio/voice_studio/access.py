"""Who is asking, and how the studio says no.

Sign-in is the backend's: the browser already holds the vaani_session cookie
that /auth/google set (backend/vaani/auth.py). Vite forwards /studio on the
same origin, so the browser sends that cookie here too. The studio checks it
with the backend's own read_cookie and the backend's own [auth] settings: the
same HMAC secret, read through the same settings object, so there is no
second copy of either. No valid cookie means 401 on every route.

Routes that change something (POST, DELETE) also need an allowed Origin
header, exactly like /auth/google and /auth/logout. The cookie is SameSite=Lax,
so other sites' POSTs never carry it; the Origin check is the second lock.

Every refusal is a StudioError, sent as {"type": "error", "code", "message"},
the shape of the backend's error messages. `message` is written for the
user: what went wrong and what to do about it.
"""

from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from vaani.asr.base import Recognizer
from vaani.auth import COOKIE_NAME, origin_allowed, read_cookie
from vaani.config import AuthSettings

from voice_studio.config import StudioSettings
from voice_studio.store import Store, user_id
from voice_studio.verify import Challenge


class StudioError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


async def studio_error_response(_request: Request, exc: StudioError) -> JSONResponse:
    body = {"type": "error", "code": exc.code, "message": exc.message}
    return JSONResponse(body, status_code=exc.status)


@dataclass
class Studio:
    """Everything the routes share, kept on app.state.studio."""

    cfg: StudioSettings
    auth: AuthSettings
    store: Store
    cloner: object  # model.Cloner, or a fake in tests
    encoder: object  # model.SpeakerEncoder, or a fake in tests
    recognizer: Recognizer
    # The live challenge phrase of each user, by user id (verify.py).
    challenges: dict[str, Challenge] = field(default_factory=dict)
    # True while a generation holds the model. Read and set on the event
    # loop's thread with no await in between, so two requests can never
    # both see False (the same reasoning as vaani/spend.py's cap).
    busy: bool = False


@dataclass(frozen=True)
class User:
    uid: str
    email: str
    name: str


def studio_of(request: Request) -> Studio:
    return request.app.state.studio


def signed_in(request: Request) -> User:
    """FastAPI dependency: the signed-in user, or 401."""
    studio = studio_of(request)
    user = read_cookie(request.cookies.get(COOKIE_NAME), studio.auth)
    if user is None:
        raise StudioError(401, "AUTH_REQUIRED", "Sign in first.")
    return User(user_id(user["email"]), user["email"], user["name"])


def signed_in_writer(request: Request) -> User:
    """FastAPI dependency for POST and DELETE: signed in AND an allowed Origin."""
    user = signed_in(request)
    if not origin_allowed(request.headers.get("origin"), studio_of(request).auth):
        raise StudioError(403, "AUTH_BAD_ORIGIN", "This page's origin is not allowed.")
    return user


# Route parameters typed with these get the user from the dependency above:
# FastAPI runs it before the route, and its StudioError becomes the answer.
Reader = Annotated[User, Depends(signed_in)]
Writer = Annotated[User, Depends(signed_in_writer)]
