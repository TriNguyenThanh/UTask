"""HTTP error envelope; không phát tán token/raw validation input."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from errors import ServiceError, failure, public_error


def error_response(request: Request, error: ServiceError) -> JSONResponse:
    error = public_error(error)
    return JSONResponse(
        status_code=error.status_code,
        content={
            "error": {
                "code": error.code,
                "message": error.message,
                "details": error.details,
                "request_id": error.request_id or getattr(request.state, "trace_id", None),
                "retryable": error.retryable,
            }
        },
    )


async def handle_service_error(request: Request, error: ServiceError) -> JSONResponse:
    return error_response(request, error)


async def handle_validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
    fields = [".".join(str(part) for part in item["loc"]) for item in error.errors()]
    return error_response(
        request,
        ServiceError("INVALID_INPUT", "Request không hợp lệ.", 422, details={"fields": fields}),
    )


async def handle_internal_error(request: Request, error: Exception) -> JSONResponse:
    return error_response(request, failure("INTERNAL_ERROR", 500))


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ServiceError, handle_service_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_internal_error)
