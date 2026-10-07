"""Chuyển lỗi application thành error envelope HTTP."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from errors import ServiceError


async def handle_service_error(request: Request, error: ServiceError) -> JSONResponse:
    payload = {
        "error": {
            "code": error.code,
            "message": error.message,
            "details": error.details,
            "request_id": error.request_id,
            "retryable": error.retryable,
        }
    }
    return JSONResponse(status_code=error.status_code, content=payload)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ServiceError, handle_service_error)
