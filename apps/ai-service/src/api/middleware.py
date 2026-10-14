"""Gắn trace ID cho request và response."""

from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from fastapi import Request, Response

from errors import failure

from .exception_handlers import error_response


async def request_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    try:
        trace_id = str(UUID(request.headers.get("X-Request-ID", "")))
    except ValueError:
        trace_id = str(uuid4())
    request.state.trace_id = trace_id
    try:
        response = await call_next(request)
    except Exception:
        response = error_response(request, failure("INTERNAL_ERROR", 500))
    response.headers["X-Request-ID"] = trace_id
    return response
