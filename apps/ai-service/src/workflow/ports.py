"""Hợp đồng context và model dùng bởi bounded workflow."""

from typing import Protocol

from models import CreateAiRequest
from models.budget import Charge as Charge
from models.context import ContextDocument
from models.security import Principal


class ContextGateway(Protocol):
    async def fetch(
        self, domain: str, principal: Principal, request: CreateAiRequest
    ) -> ContextDocument: ...
