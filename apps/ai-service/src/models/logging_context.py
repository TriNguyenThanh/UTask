"""Correlation ID cục bộ mỗi lần thực thi; không chứa credential/context."""

from contextlib import contextmanager
from contextvars import ContextVar

request_id_context: ContextVar[str | None] = ContextVar("ai_request_id", default=None)


@contextmanager
def bind_request_id(request_id: str):
    token = request_id_context.set(request_id)
    try:
        yield
    finally:
        request_id_context.reset(token)
