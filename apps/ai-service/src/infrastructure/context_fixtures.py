"""Context/quyền mẫu cho service chưa có; không mở server HTTP riêng."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import model_validator

from config import Settings
from errors import failure
from models import CreateAiRequest
from models.common import StrictModel
from models.context import ContextDocument
from models.security import Principal

from .context_http import ALLOWED_FIELDS, filter_data

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "domain.json"
Domain = Literal["project", "task", "team", "progress", "github_activity"]


class TargetFixture(StrictModel):
    allowed_users: list[str]
    contexts: dict[Domain, str]


class ContextFixture(StrictModel):
    domain: Domain
    data: dict[str, object]


class DatasetFixture(StrictModel):
    targets: dict[str, TargetFixture]
    documents: dict[str, ContextFixture]

    @model_validator(mode="after")
    def valid_references(self):
        for key, target in self.targets.items():
            target_type, target_id = key.split(":", 1)
            if target_type not in {"project", "task", "sprint"}:
                raise ValueError("Target mock không hợp lệ")
            if str(UUID(target_id)) != target_id:
                raise ValueError("ID mock phải là UUID canonical")
            for domain, name in target.contexts.items():
                if name not in self.documents or self.documents[name].domain != domain:
                    raise ValueError("Context reference thiếu hoặc sai domain")
        return self


def load_mock_dataset(path: Path = FIXTURE_PATH) -> DatasetFixture:
    return DatasetFixture.model_validate_json(path.read_text(encoding="utf-8"))


class FixtureContextAdapter:
    def __init__(self, settings: Settings, fixture_path: Path = FIXTURE_PATH):
        if not settings.mock_test or settings.environment not in {"development", "test"}:
            raise ValueError("Fixture adapter chỉ dùng khi bật MOCK_TEST trong development/test")
        self.dataset = load_mock_dataset(fixture_path)

    async def authorize(self, principal: Principal, request: CreateAiRequest) -> None:
        if request.target is None:
            return
        target = self.dataset.targets.get(f"{request.target.type}:{request.target.id}")
        if target is None or principal.user_id not in target.allowed_users:
            raise failure("TARGET_ACCESS_DENIED", 403)

    async def fetch(
        self, domain: str, principal: Principal, request: CreateAiRequest
    ) -> ContextDocument:
        if domain not in ALLOWED_FIELDS or request.target is None:
            raise failure("CONTEXT_INVALID")
        await self.authorize(principal, request)
        target = self.dataset.targets[f"{request.target.type}:{request.target.id}"]
        if domain not in target.contexts:
            raise failure("CONTEXT_UNAVAILABLE")
        document = self.dataset.documents[target.contexts[domain]]
        return ContextDocument(
            domain=domain,
            as_of=datetime.now(UTC),
            status="available",
            source_version="mock.v1",
            data={
                key: filter_data(value)
                for key, value in document.data.items()
                if key in ALLOWED_FIELDS[domain]
            },
            warning="Dữ liệu mock local, không phải dữ liệu Work/Integration thật.",
        )
