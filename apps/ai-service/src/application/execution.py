"""Xử lý một job; Celery task chỉ gọi use case này."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError

from errors import ServiceError, failure
from models import SucceededAiResponse
from models.budget import BudgetKind
from models.validation import validate_result

from .ports import Authenticator, Authorizer, CredentialVault, RequestExecutor, RequestRepository
from .responses import failed_response


class RequestWorker:
    def __init__(
        self,
        repository: RequestRepository,
        authenticator: Authenticator,
        authorizer: Authorizer,
        vault: CredentialVault,
        executor: RequestExecutor,
    ):
        self.repository = repository
        self.authenticator = authenticator
        self.authorizer = authorizer
        self.vault = vault
        self.executor = executor

    async def execute(self, request_id: UUID) -> bool:
        stored = await asyncio.to_thread(self.repository.claim, request_id, datetime.now(UTC))
        if stored is None:
            return False

        async def charge(kind: BudgetKind, limit: int, amount: int = 1) -> int:
            allowed = await asyncio.to_thread(
                self.repository.consume,
                request_id,
                stored.execution_token,
                kind,
                limit,
                datetime.now(UTC),
                amount,
            )
            if allowed is None:
                raise failure("BUDGET_EXCEEDED", 429)
            return allowed

        try:
            remaining = (stored.deadline - datetime.now(UTC)).total_seconds()
            async with asyncio.timeout(max(0, remaining)):
                principal = await self.authenticator.authenticate(
                    self.vault.open(stored.credential)
                )
                if principal.user_id != stored.user_id:
                    raise failure("AUTHENTICATION_REQUIRED", 401)
                await self.authorizer.authorize(principal, stored.payload)
                response = await self.executor.execute(stored, principal, charge)
                if (
                    not isinstance(response, SucceededAiResponse)
                    or response.request_id != request_id
                    or response.intent != stored.payload.intent
                    or response.output_schema_version != stored.payload.output_schema_version
                ):
                    raise failure("OUTPUT_VALIDATION_FAILED", 422)
                try:
                    validate_result(stored.payload.intent, response.result)
                except (ValidationError, ValueError):
                    raise failure("OUTPUT_VALIDATION_FAILED", 422) from None
        except TimeoutError:
            response = failed_response(
                stored.payload,
                request_id,
                stored.response.created_at,
                datetime.now(UTC),
                failure("WORKFLOW_TIMEOUT", 504),
            )
        except ServiceError as error:
            response = failed_response(
                stored.payload, request_id, stored.response.created_at, datetime.now(UTC), error
            )
        except Exception:
            response = failed_response(
                stored.payload,
                request_id,
                stored.response.created_at,
                datetime.now(UTC),
                failure("INTERNAL_ERROR", 500),
            )
        return await asyncio.to_thread(
            self.repository.finish, request_id, stored.execution_token, response, datetime.now(UTC)
        )
