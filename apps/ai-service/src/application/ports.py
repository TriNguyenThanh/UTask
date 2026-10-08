"""Hợp đồng application; không phụ thuộc framework hoặc adapter cụ thể."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from models import AiResponse, CreateAiRequest, SucceededAiResponse
from models.budget import BudgetKind, Charge
from models.security import Principal


@dataclass(frozen=True)
class StoredRequest:
    request_id: UUID
    user_id: str
    payload: CreateAiRequest
    response: AiResponse
    credential: str = field(repr=False)
    execution_token: UUID | None = None
    deadline: datetime | None = None


@dataclass(frozen=True)
class Delivery:
    request_id: UUID
    token: UUID
    attempts: int


class Authenticator(Protocol):
    async def authenticate(self, bearer: str) -> Principal: ...


class Authorizer(Protocol):
    async def authorize(self, principal: Principal, request: CreateAiRequest) -> None: ...


class CredentialVault(Protocol):
    def seal(self, bearer: str) -> str: ...
    def open(self, credential: str) -> str: ...


class RequestExecutor(Protocol):
    async def execute(
        self, stored: StoredRequest, principal: Principal, charge: Charge
    ) -> SucceededAiResponse: ...


class RequestRepository(Protocol):
    def enqueue(
        self, payload: CreateAiRequest, user_id: str, key: str, credential: str, now: datetime
    ) -> StoredRequest: ...
    def get(self, request_id: UUID) -> StoredRequest | None: ...
    def claim(self, request_id: UUID, now: datetime) -> StoredRequest | None: ...
    def finish(
        self, request_id: UUID, token: UUID, response: AiResponse, now: datetime
    ) -> bool: ...
    def consume(
        self,
        request_id: UUID,
        token: UUID,
        kind: BudgetKind,
        limit: int,
        now: datetime,
        amount: int = 1,
    ) -> int | None: ...
    def deliveries(self, now: datetime, limit: int = 100) -> list[Delivery]: ...
    def delivered(self, delivery: Delivery, now: datetime) -> None: ...
    def delivery_failed(self, delivery: Delivery, now: datetime) -> None: ...
    def expire(self, now: datetime) -> int: ...


class JobPublisher(Protocol):
    def publish(self, request_id: UUID) -> None: ...
