"""Route chỉ nhận dữ liệu HTTP, gọi application và trả JSON."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse

from application import AiApplicationService
from models.requests import CreateAiRequest

from .dependencies import get_application, get_requester_user_id

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/api/ai/v1/requests")
async def create_request(
    payload: CreateAiRequest,
    application: Annotated[AiApplicationService, Depends(get_application)],
    requester_user_id: Annotated[str, Depends(get_requester_user_id)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=256)],
) -> JSONResponse:
    response = await application.create_request(
        payload,
        requester_user_id=requester_user_id,
        idempotency_key=idempotency_key,
    )
    return JSONResponse(status_code=200, content=response.model_dump(mode="json", by_alias=True))


@router.get("/api/ai/v1/requests/{request_id}")
async def get_request(
    request_id: UUID,
    application: Annotated[AiApplicationService, Depends(get_application)],
    requester_user_id: Annotated[str, Depends(get_requester_user_id)],
) -> JSONResponse:
    response = application.get_request(request_id, requester_user_id=requester_user_id)
    return JSONResponse(status_code=200, content=response.model_dump(mode="json", by_alias=True))
