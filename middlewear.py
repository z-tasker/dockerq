#!/usr/bin/env python3
from __future__ import annotations

import base64
import os

from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.authentication import (
    AuthenticationBackend,
    AuthenticationError,
    SimpleUser,
    AuthCredentials,
)
from starlette.requests import Request
from starlette.responses import JSONResponse

from log import get_logger


def get_users_from_env() -> Dict[str, str]:
    users = dict()
    for name, value in os.environ.items():
        if name.startswith("DOCKERQ_USER_") and name.endswith("_PASSWORD"):
            users[name.replace("DOCKERQ_USER_", "").replace("_PASSWORD", "").lower()] = value
    return users


class BasicAuthBackend(AuthenticationBackend):
    def __init__(self) -> None:
        self.users = get_users_from_env()
        self.log = get_logger("auth")
        self.log.info(f"loaded {len(self.users)} users from environment")

    async def authenticate(
        self, request: Request
    ) -> Tuple[AuthCredentials, SimpleUser]:
        if "Authorization" not in request.headers:
            return

        auth = request.headers["Authorization"]
        try:
            scheme, credentials = auth.split()
            if scheme.lower() != "basic":
                return
            decoded = base64.b64decode(credentials).decode("ascii")
        except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
            raise AuthenticationError("Invalid basic auth credentials")

        username, _, password = decoded.partition(":")
        try:
            assert password == self.users[username]
        except (AssertionError, KeyError) as exc:
            raise AuthenticationError(f"Username or Password incorrect for {username}.")

        request.app.state.log.debug(f"authenticated {username}")
        return AuthCredentials(["authenticated"]), SimpleUser(username)


def on_auth_error(request: Request, exc: Exception):
    return JSONResponse({"error": str(exc)}, status_code=401)


def get_middlewear() -> List[Middlewear]:
    return [
        Middleware(
            AuthenticationMiddleware, backend=BasicAuthBackend(), on_error=on_auth_error
        )
    ]
