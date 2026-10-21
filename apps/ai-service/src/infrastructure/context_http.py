"""HTTP adapter tới URL đã cấu hình; agent không chọn URL hay credential."""

import json
import logging
from datetime import UTC, datetime
from time import monotonic
from typing import get_args, get_origin
from urllib.parse import quote

import httpx
from pydantic import BaseModel, SecretStr, ValidationError

from config import WORK_CONTEXT_PAIRS, Settings, valid_internal_url
from errors import ServiceError, failure
from models import CreateAiRequest, Intent
from models.context import CONTEXT_DATA_SCHEMAS, ContextDocument
from models.security import Principal

from .observability import configure_context_logging, request_id_context

logger = logging.getLogger(__name__)
ALLOWED_FIELDS = {
    domain: set(schema.model_fields) for domain, schema in CONTEXT_DATA_SCHEMAS.items()
}


def _select_fields(value: object, annotation: object) -> object:
    """Loại dữ liệu ngoài allowlist trước validation, không ép kiểu giá trị nguồn."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if not isinstance(value, dict):
            return value
        return {
            key: _select_fields(item, annotation.model_fields[key].annotation)
            for key, item in value.items()
            if key in annotation.model_fields
        }
    if get_origin(annotation) is list and isinstance(value, list):
        item_type = get_args(annotation)[0]
        return [_select_fields(item, item_type) for item in value]
    return value


def validate_context_data(document: ContextDocument) -> ContextDocument:
    schema = CONTEXT_DATA_SCHEMAS[document.domain]
    if document.status == "missing" and document.domain != "github_activity":
        return document.model_copy(update={"data": {}})
    try:
        filtered = (
            document.data
            if document.domain == "github_activity"
            else _select_fields(document.data, schema)
        )
        data = schema.model_validate_json(
            json.dumps(filtered, allow_nan=False), strict=True
        ).model_dump(mode="json", exclude_unset=True)
    except (ValidationError, ValueError, TypeError) as error:
        raise failure("CONTEXT_INVALID") from error
    return document.model_copy(update={"data": data})


class InternalContextAdapter:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings = settings
        self.client = client
        configure_context_logging()

    def _url(self, template: str | None, request: CreateAiRequest) -> str:
        if not template or request.target is None or not valid_internal_url(template):
            raise failure("CONTEXT_UNAVAILABLE")
        return template.format(
            target_type=quote(request.target.type, safe=""),
            target_id=quote(str(request.target.id), safe=""),
        )

    async def _request(
        self,
        method: str,
        url: str,
        principal: Principal,
        service_key: SecretStr | None,
        *,
        body: dict | None = None,
    ) -> tuple[dict, int]:
        if service_key is None or not service_key.get_secret_value().strip():
            raise failure("CONTEXT_UNAVAILABLE")
        try:
            async with self.client.stream(
                method,
                url,
                headers={
                    "Authorization": f"Bearer {principal.bearer}",
                    "X-Service-Key": service_key.get_secret_value(),
                },
                json=body,
                timeout=self.settings.http_timeout_seconds,
                follow_redirects=False,
            ) as response:
                if response.status_code in {401, 403, 404}:
                    raise failure("TARGET_ACCESS_DENIED", 403)
                if response.status_code != 200:
                    raise failure(
                        "CONTEXT_UNAVAILABLE",
                        retryable=response.status_code == 429 or response.status_code >= 500,
                    )
                body_bytes = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body_bytes) + len(chunk) > self.settings.max_context_bytes:
                        raise failure("CONTEXT_INVALID")
                    body_bytes.extend(chunk)
                payload = json.loads(body_bytes)
                if not isinstance(payload, dict):
                    raise failure("CONTEXT_INVALID")
                return payload, len(body_bytes)
        except httpx.HTTPError as error:
            raise failure("CONTEXT_UNAVAILABLE", retryable=True) from error
        except (ValueError, UnicodeError, RecursionError) as error:
            raise failure("CONTEXT_INVALID") from error

    async def authorize(self, principal: Principal, request: CreateAiRequest) -> None:
        if request.target is None:
            return
        url = self._url(self.settings.authorization_urls.get(request.target.type), request)
        payload, _ = await self._request(
            "POST",
            url,
            principal,
            self.settings.work_service_key,
            body={"action": "ai.analyze", "intent": request.intent.value},
        )
        decision = payload.get("data")
        if (
            payload.get("success") is not True
            or not {"success", "data"} <= payload.keys()
            or not payload.keys() <= {"success", "data", "message", "meta", "error"}
            or not isinstance(decision, dict)
            or set(decision) != {"target_type", "target_id", "action", "allowed"}
            or decision.get("target_type") != request.target.type
            or decision.get("target_id") != str(request.target.id)
            or decision.get("action") != "ai.analyze"
            or type(decision.get("allowed")) is not bool
        ):
            raise failure("CONTEXT_INVALID")
        if decision["allowed"] is not True:
            raise failure("TARGET_ACCESS_DENIED", 403)

    async def fetch(
        self, domain: str, principal: Principal, request: CreateAiRequest
    ) -> ContextDocument:
        started = monotonic()
        error_code = None
        status = None
        retryable = False
        payload_bytes = None
        provider = "integration" if domain == "github_activity" else "work"
        try:
            if domain not in ALLOWED_FIELDS or request.target is None:
                raise failure("CONTEXT_INVALID")
            pair = f"{request.target.type}:{domain}"
            if domain == "github_activity":
                if (
                    not self.settings.github_context_enabled
                    or request.target.type != "project"
                    or request.intent != Intent.RISK_ANALYSIS
                    or (request.input.focus and "github_activity" not in request.input.focus)
                ):
                    raise failure("CONTEXT_INVALID")
                key = self.settings.integration_service_key
            else:
                if pair not in WORK_CONTEXT_PAIRS:
                    raise failure("CONTEXT_INVALID")
                await self.authorize(principal, request)
                key = self.settings.work_service_key
            raw, payload_bytes = await self._request(
                "GET", self._url(self.settings.context_urls.get(pair), request), principal, key
            )
            try:
                document = ContextDocument.model_validate(raw)
            except ValidationError as error:
                raise failure("CONTEXT_INVALID") from error
            if document.domain != domain or document.as_of.tzinfo is None:
                raise failure("CONTEXT_INVALID")
            if (
                not {"domain", "as_of", "status", "source_version", "data", "warning"} <= raw.keys()
                or not isinstance(raw.get("as_of"), str)
                or (document.source_version is not None and len(document.source_version) > 100)
                or (document.warning is not None and len(document.warning) > 500)
                or (
                    domain != "github_activity"
                    and document.status == "partial"
                    and not document.warning
                )
            ):
                raise failure("CONTEXT_INVALID")
            status = document.status
            age = (datetime.now(UTC) - document.as_of).total_seconds()
            if age < -30:
                raise failure("CONTEXT_INVALID")
            if age > self.settings.context_max_age_seconds or document.status == "stale":
                raise failure("CONTEXT_STALE")
            if document.status == "unavailable":
                raise failure("CONTEXT_UNAVAILABLE", retryable=True)
            document = validate_context_data(document)
            return document
        except ServiceError as error:
            error_code = error.code
            retryable = error.retryable
            raise
        finally:
            logger.info(
                "ai_context_fetch",
                extra={
                    "request_id": request_id_context.get(),
                    "provider": provider,
                    "domain": domain if domain in ALLOWED_FIELDS else "invalid",
                    "target_type": request.target.type if request.target else None,
                    "context_status": status,
                    "error_code": error_code,
                    "retryable": retryable,
                    "duration_ms": round((monotonic() - started) * 1000, 2),
                    "payload_bytes": payload_bytes,
                },
            )
