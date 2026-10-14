"""HTTP transport: application nhận job, API đọc trạng thái persistence."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse

from application import AiApplicationService
from models.requests import CreateAiRequest
from models.security import Principal

from .dependencies import get_application, get_principal

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/api/ai/v1/requests")
async def create_request(
    payload: CreateAiRequest,
    application: Annotated[AiApplicationService, Depends(get_application)],
    principal: Annotated[Principal, Depends(get_principal)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=256)],
) -> JSONResponse:
    response = await application.create_request(
        payload, principal=principal, idempotency_key=idempotency_key
    )
    accepted = response.status == "queued"
    return JSONResponse(
        status_code=202 if accepted else 200,
        content=response.model_dump(mode="json", by_alias=True, exclude_none=True),
        headers={"Location": response.status_url} if accepted else {},
    )


@router.get("/api/ai/v1/requests/{request_id}")
async def get_request(
    request_id: UUID,
    application: Annotated[AiApplicationService, Depends(get_application)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> JSONResponse:
    response = await application.get_request(request_id, principal=principal)
    return JSONResponse(
        status_code=200, content=response.model_dump(mode="json", by_alias=True, exclude_none=True)
    )
