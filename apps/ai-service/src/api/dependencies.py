"""Các dependency được FastAPI cấp cho route handler."""

from typing import Annotated

from fastapi import Header, Request

from application import AiApplicationService
from errors import AuthenticationRequiredError


def get_application(request: Request) -> AiApplicationService:
    return request.app.state.application


def get_requester_user_id(
    authenticated_user_id: Annotated[str | None, Header(alias="X-Authenticated-User-ID")] = None,
) -> str:
    """Đọc identity header của bootstrap; chưa triển khai xác minh gateway/token."""

    if not authenticated_user_id:
        raise AuthenticationRequiredError()
    return authenticated_user_id
