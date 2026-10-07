"""Gắn trace ID cho request và response."""

from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request, Response


async def request_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    trace_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.trace_id = trace_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = trace_id
    return response
