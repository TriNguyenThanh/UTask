"""Log context dạng JSON với allowlist metadata, không chứa dữ liệu nguồn."""

import json
import logging

from models.logging_context import bind_request_id, request_id_context

__all__ = ["bind_request_id", "request_id_context", "configure_context_logging"]


class ContextJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        fields = (
            "request_id",
            "provider",
            "domain",
            "target_type",
            "context_status",
            "error_code",
            "retryable",
            "duration_ms",
            "payload_bytes",
        )
        return json.dumps(
            {"event": "ai_context_fetch", **{key: getattr(record, key, None) for key in fields}},
            ensure_ascii=False,
        )


def configure_context_logging() -> None:
    logger = logging.getLogger("infrastructure.context_http")
    if not any(getattr(handler, "ai_context_handler", False) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.ai_context_handler = True
        handler.setFormatter(ContextJsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
