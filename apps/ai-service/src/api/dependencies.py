"""HTTP dependencies chỉ cung cấp use case và identity đã xác minh."""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from errors import failure
from models.security import Principal

bearer_scheme = HTTPBearer(auto_error=False)


def get_application(request: Request):
    return request.app.state.application


async def get_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> Principal:
    if credentials is None:
        raise failure("AUTHENTICATION_REQUIRED", 401)
    return await request.app.state.authenticator.authenticate(credentials.credentials)
