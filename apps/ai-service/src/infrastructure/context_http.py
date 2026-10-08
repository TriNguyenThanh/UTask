"""HTTP adapter tới URL đã cấu hình; agent không chọn URL hay credential."""

import json
from datetime import UTC, datetime
from urllib.parse import quote, urlsplit

import httpx
from pydantic import ValidationError

from config import Settings
from errors import failure
from models import CreateAiRequest
from models.context import ContextDocument
from models.security import Principal

# Chỉ đưa trường domain đã được review vào prompt, bỏ token/secret/metadata hạ tầng.
ALLOWED_FIELDS = {
    "project": {"id", "name", "description", "goals", "deadline", "tasks", "sprints"},
    "task": {
        "id",
        "title",
        "description",
        "status",
        "priority",
        "deadline",
        "dependencies",
        "acceptance_criteria",
        "estimate_points",
        "project_id",
    },
    "team": {"members", "workload", "capacity"},
    "progress": {"metrics", "blocked_tasks", "completed_tasks", "total_tasks", "as_of"},
    "github_activity": {"commits", "pull_requests", "issues", "mapping_status"},
}
NESTED_FIELDS = {
    "id",
    "name",
    "title",
    "description",
    "status",
    "priority",
    "deadline",
    "estimate_points",
    "dependencies",
    "acceptance_criteria",
    "user_id",
    "capacity",
    "workload",
    "value",
    "unit",
    "observed_at",
    "task_id",
    "project_id",
    "occurred_at",
    "merged_at",
    "created_at",
    "updated_at",
    "count",
    "state",
}


def filter_data(value: object, depth: int = 0) -> object:
    if depth > 5:
        raise failure("CONTEXT_INVALID")
    if isinstance(value, dict):
        return {
            key: filter_data(item, depth + 1) for key, item in value.items() if key in NESTED_FIELDS
        }
    if isinstance(value, list):
        return [filter_data(item, depth + 1) for item in value[:100]]
    if isinstance(value, str):
        return value[:4000]
    return value


class InternalContextAdapter:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings = settings
        self.client = client

    def _url(self, template: str | None, request: CreateAiRequest) -> str:
        if not template or request.target is None:
            raise failure("CONTEXT_UNAVAILABLE")
        url = template.format(
            target_type=quote(request.target.type, safe=""),
            target_id=quote(str(request.target.id), safe=""),
        )
        parts = urlsplit(url)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username
            or parts.fragment
        ):
            raise failure("CONTEXT_UNAVAILABLE")
        return url

    async def _get(self, url: str, principal: Principal) -> dict:
        try:
            async with self.client.stream(
                "GET",
                url,
                headers={"Authorization": f"Bearer {principal.bearer}"},
                timeout=self.settings.http_timeout_seconds,
                follow_redirects=False,
            ) as response:
                if response.status_code in {401, 403}:
                    raise failure("TARGET_ACCESS_DENIED", 403)
                if response.status_code != 200:
                    raise failure("CONTEXT_UNAVAILABLE", retryable=response.status_code >= 500)
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > self.settings.max_context_bytes:
                        raise failure("CONTEXT_INVALID")
                payload = json.loads(body)
                if not isinstance(payload, dict):
                    raise failure("CONTEXT_INVALID")
                return payload
        except httpx.HTTPError as error:
            raise failure("CONTEXT_UNAVAILABLE", retryable=True) from error
        except (ValueError, UnicodeError) as error:
            raise failure("CONTEXT_INVALID") from error

    async def authorize(self, principal: Principal, request: CreateAiRequest) -> None:
        if request.target is None:
            return
        url = self._url(self.settings.authorization_urls.get(request.target.type), request)
        payload = await self._get(url, principal)
        # Adapter contract phải trả quyết định rõ ràng; không coi HTTP 200 là quyền.
        if payload.get("allowed") is not True:
            raise failure("TARGET_ACCESS_DENIED", 403)

    async def fetch(
        self, domain: str, principal: Principal, request: CreateAiRequest
    ) -> ContextDocument:
        if domain not in ALLOWED_FIELDS:
            raise failure("CONTEXT_INVALID")
        await self.authorize(principal, request)
        url = self._url(
            self.settings.context_urls.get(f"{request.target.type}:{domain}")
            if request.target
            else None,
            request,
        )
        raw = await self._get(url, principal)
        try:
            document = ContextDocument.model_validate(raw)
        except ValidationError as error:
            raise failure("CONTEXT_INVALID") from error
        if document.domain != domain or document.as_of.tzinfo is None:
            raise failure("CONTEXT_INVALID")
        age = (datetime.now(UTC) - document.as_of).total_seconds()
        if age < -30:
            raise failure("CONTEXT_INVALID")
        if document.status in {"missing", "unavailable"}:
            raise failure("CONTEXT_UNAVAILABLE")
        if age > self.settings.context_max_age_seconds or document.status == "stale":
            raise failure("CONTEXT_STALE")
        filtered = {
            key: filter_data(value)
            for key, value in document.data.items()
            if key in ALLOWED_FIELDS[domain]
        }
        return document.model_copy(update={"data": filtered})
