"""Domain tool pool gắn với đúng target, không nhận ID/URL từ agent."""

import hashlib
import json
from datetime import UTC, datetime

from errors import failure
from models import ContextMetadata, ContextSource, CreateAiRequest, Intent
from models.context import ContextDocument
from models.security import Principal
from workflow.ports import Charge, ContextGateway


class ContextToolPool:
    def __init__(
        self,
        gateway: ContextGateway,
        principal: Principal,
        request: CreateAiRequest,
        charge: Charge,
        max_calls: int,
    ):
        self.gateway = gateway
        self.principal = principal
        self.request = request
        self.charge = charge
        self.max_calls = max_calls
        self.documents: dict[str, ContextDocument] = {}

    async def _fetch(self, domain: str) -> dict:
        if self.request.target is None:
            raise failure("CONTEXT_INVALID")
        await self.charge("tool", self.max_calls)
        document = await self.gateway.fetch(domain, self.principal, self.request)
        self.documents[domain] = document
        return document.model_dump(mode="json")

    def validate_context(self) -> None:
        """Kiểm tra context thiết yếu; agent vẫn tự chọn thứ tự và tool bổ sung."""
        if self.request.target is None:
            return
        required = {
            Intent.BACKLOG_GENERATION: "project",
            Intent.TASK_DECOMPOSITION: "task",
            Intent.RISK_ANALYSIS: "progress",
        }[self.request.intent]
        if required not in self.documents:
            raise failure("CONTEXT_UNAVAILABLE")

    async def get_task_context(self) -> dict:
        """Lấy task hiện tại đã được cấp quyền, không tự chọn task khác."""
        if self.request.target is None or self.request.target.type != "task":
            raise failure("CONTEXT_INVALID")
        return await self._fetch("task")

    async def get_project_context(self) -> dict:
        """Lấy thông tin project trong phạm vi target đã xác thực."""
        return await self._fetch("project")

    async def get_team_context(self) -> dict:
        """Lấy thành viên và workload đã lọc trong phạm vi target."""
        return await self._fetch("team")

    async def get_progress_context(self) -> dict:
        """Lấy chỉ số tiến độ đã được Work tính bằng quy tắc."""
        return await self._fetch("progress")

    async def get_development_context(self) -> dict:
        """Lấy hoạt động GitHub đã chuẩn hóa từ Integration."""
        return await self._fetch("github_activity")

    def tools(self) -> list:
        if self.request.target is None:
            return []
        tools = [
            self.get_project_context,
            self.get_team_context,
            self.get_progress_context,
            self.get_development_context,
        ]
        if self.request.target.type == "task":
            tools.append(self.get_task_context)
        return tools

    def metadata(self) -> ContextMetadata:
        payload = {
            name: doc.model_dump(mode="json") for name, doc in sorted(self.documents.items())
        }
        sources = [
            ContextSource(
                domain=doc.domain,
                status=doc.status,
                as_of=doc.as_of,
                source_version=doc.source_version,
                warning=doc.warning,
            )
            for doc in self.documents.values()
        ]
        return ContextMetadata(
            as_of=min((doc.as_of for doc in self.documents.values()), default=datetime.now(UTC)),
            sources=sources,
            fingerprint=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
        )
