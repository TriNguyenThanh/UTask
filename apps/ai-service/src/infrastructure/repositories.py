"""Repository PostgreSQL; transaction và lock bảo vệ giao job/idempotency."""

import hashlib
import json
from datetime import datetime, timedelta
from random import uniform
from uuid import UUID, uuid4

from pydantic import TypeAdapter
from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import sessionmaker

from application.ports import Delivery, StoredRequest
from application.responses import failed_response
from errors import failure
from models import AiResponse, CreateAiRequest, QueuedAiResponse, RunningAiResponse

from .db.tables import DeadLetterRow, DeliveryRow, RequestRow

REQUEST_ADAPTER = TypeAdapter(CreateAiRequest)
RESPONSE_ADAPTER = TypeAdapter(AiResponse)


def fingerprint(payload: CreateAiRequest) -> str:
    canonical = json.dumps(
        payload.model_dump(mode="json", by_alias=True), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def record(row: RequestRow) -> StoredRequest:
    return StoredRequest(
        row.id,
        row.user_id,
        REQUEST_ADAPTER.validate_python(row.payload),
        RESPONSE_ADAPTER.validate_python(row.response),
        row.credential,
        row.execution_token,
        row.execution_deadline,
    )


class PostgresRequestRepository:
    def __init__(
        self,
        sessions: sessionmaker,
        *,
        queue_timeout: float = 300,
        workflow_timeout: float = 30,
        dispatch_lease: float = 10,
        redelivery: float = 15,
        max_dispatch_attempts: int = 8,
    ):
        self.sessions = sessions
        self.queue_timeout = queue_timeout
        self.workflow_timeout = workflow_timeout
        self.dispatch_lease = dispatch_lease
        self.redelivery = redelivery
        self.max_dispatch_attempts = max_dispatch_attempts

    def enqueue(
        self, payload: CreateAiRequest, user_id: str, key: str, credential: str, now: datetime
    ) -> StoredRequest:
        request_id = uuid4()
        response = QueuedAiResponse(
            request_id=request_id,
            intent=payload.intent,
            output_schema_version=payload.output_schema_version,
            status="queued",
            created_at=now,
            updated_at=now,
            status_url=f"/api/ai/v1/requests/{request_id}",
        )
        with self.sessions.begin() as session:
            created = session.execute(
                insert(RequestRow)
                .values(
                    id=request_id,
                    user_id=user_id,
                    idempotency_key=key,
                    fingerprint=fingerprint(payload),
                    payload=payload.model_dump(mode="json", by_alias=True),
                    response=response.model_dump(mode="json"),
                    status="queued",
                    credential=credential,
                    created_at=now,
                    queue_expires_at=now + timedelta(seconds=self.queue_timeout),
                    model_calls=0,
                    tool_calls=0,
                    output_tokens=0,
                )
                .on_conflict_do_nothing(
                    index_elements=[RequestRow.user_id, RequestRow.idempotency_key]
                )
                .returning(RequestRow.id)
            ).scalar_one_or_none()
            if created:
                session.add(DeliveryRow(request_id=created, next_attempt_at=now, attempts=0))
            row = session.scalars(
                select(RequestRow).where(
                    RequestRow.user_id == user_id, RequestRow.idempotency_key == key
                )
            ).one()
            if row.fingerprint != fingerprint(payload):
                raise failure("IDEMPOTENCY_CONFLICT", 409)
            return record(row)

    def get(self, request_id: UUID) -> StoredRequest | None:
        with self.sessions() as session:
            row = session.get(RequestRow, request_id)
            return record(row) if row else None

    def claim(self, request_id: UUID, now: datetime) -> StoredRequest | None:
        with self.sessions.begin() as session:
            row = session.scalars(
                select(RequestRow).where(RequestRow.id == request_id).with_for_update()
            ).one_or_none()
            if row is None or row.status != "queued":
                return None
            if row.queue_expires_at <= now:
                self._fail(session, row, "QUEUE_TIMEOUT", now)
                return None
            row.status = "running"
            row.execution_token = uuid4()
            row.execution_deadline = now + timedelta(seconds=self.workflow_timeout)
            payload = REQUEST_ADAPTER.validate_python(row.payload)
            row.response = RunningAiResponse(
                request_id=row.id,
                intent=payload.intent,
                status="running",
                output_schema_version=payload.output_schema_version,
                created_at=row.created_at,
                updated_at=now,
            ).model_dump(mode="json")
            session.execute(delete(DeliveryRow).where(DeliveryRow.request_id == row.id))
            return record(row)

    def consume(
        self, request_id: UUID, token: UUID, kind: str, limit: int, now: datetime, amount: int = 1
    ) -> int | None:
        if amount < 0:
            raise ValueError("Budget không được âm")
        column = {
            "model": RequestRow.model_calls,
            "tool": RequestRow.tool_calls,
            "output": RequestRow.output_tokens,
        }[kind]
        with self.sessions.begin() as session:
            changed = session.execute(
                update(RequestRow)
                .where(
                    RequestRow.id == request_id,
                    RequestRow.execution_token == token,
                    RequestRow.status == "running",
                    RequestRow.execution_deadline > now,
                    column + amount <= limit,
                )
                .values({column: column + amount})
                .returning(column)
            ).scalar_one_or_none()
            return limit - changed if changed is not None else None

    def finish(self, request_id: UUID, token: UUID, response: AiResponse, now: datetime) -> bool:
        if response.status not in {"succeeded", "failed"} or response.request_id != request_id:
            raise ValueError("Chỉ ghi kết quả cuối cùng của chính request")
        with self.sessions.begin() as session:
            row = session.scalars(
                select(RequestRow).where(RequestRow.id == request_id).with_for_update()
            ).one_or_none()
            if row is None or row.status != "running" or row.execution_token != token:
                return False
            if row.execution_deadline <= now:
                self._fail(session, row, "WORKFLOW_TIMEOUT", now)
                return False
            row.status = response.status
            row.response = response.model_dump(mode="json")
            row.credential = ""
            row.execution_token = None
            if response.status == "failed":
                session.add(
                    DeadLetterRow(request_id=row.id, code=response.error.code, created_at=now)
                )
            return True

    def deliveries(self, now: datetime, limit: int = 100) -> list[Delivery]:
        with self.sessions.begin() as session:
            # Chỉ khóa delivery: tránh deadlock với worker khóa request rồi xóa delivery.
            rows = session.scalars(
                select(DeliveryRow)
                .where(DeliveryRow.next_attempt_at <= now)
                .order_by(DeliveryRow.next_attempt_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
            deliveries = []
            for row in rows:
                row.attempts += 1
                row.lease_token = uuid4()
                row.next_attempt_at = now + timedelta(seconds=self.dispatch_lease)
                deliveries.append(Delivery(row.request_id, row.lease_token, row.attempts))
            return deliveries

    def delivered(self, delivery: Delivery, now: datetime) -> None:
        with self.sessions.begin() as session:
            session.execute(
                update(DeliveryRow)
                .where(
                    DeliveryRow.request_id == delivery.request_id,
                    DeliveryRow.lease_token == delivery.token,
                )
                .values(next_attempt_at=now + timedelta(seconds=self.redelivery))
            )

    def delivery_failed(self, delivery: Delivery, now: datetime) -> None:
        if delivery.attempts >= self.max_dispatch_attempts:
            with self.sessions.begin() as session:
                row = session.scalars(
                    select(RequestRow).where(RequestRow.id == delivery.request_id).with_for_update()
                ).one_or_none()
                job = session.scalars(
                    select(DeliveryRow)
                    .where(DeliveryRow.request_id == delivery.request_id)
                    .with_for_update()
                ).one_or_none()
                if row and row.status == "queued" and job and job.lease_token == delivery.token:
                    self._fail(session, row, "DISPATCH_FAILED", now)
            return
        with self.sessions.begin() as session:
            session.execute(
                update(DeliveryRow)
                .where(
                    DeliveryRow.request_id == delivery.request_id,
                    DeliveryRow.lease_token == delivery.token,
                )
                .values(
                    next_attempt_at=now
                    + timedelta(seconds=min(60, 2**delivery.attempts) + uniform(0, 1))
                )
            )

    def expire(self, now: datetime) -> int:
        with self.sessions.begin() as session:
            rows = session.scalars(
                select(RequestRow)
                .where(
                    or_(
                        (RequestRow.status == "queued") & (RequestRow.queue_expires_at <= now),
                        (RequestRow.status == "running") & (RequestRow.execution_deadline <= now),
                    )
                )
                .with_for_update(skip_locked=True)
            ).all()
            for row in rows:
                self._fail(
                    session,
                    row,
                    "QUEUE_TIMEOUT" if row.status == "queued" else "WORKFLOW_TIMEOUT",
                    now,
                )
            return len(rows)

    def _fail(self, session, row: RequestRow, code: str, now: datetime) -> None:
        response = failed_response(
            REQUEST_ADAPTER.validate_python(row.payload), row.id, row.created_at, now, failure(code)
        )
        row.response = response.model_dump(mode="json")
        row.status = "failed"
        row.credential = ""
        row.execution_token = None
        session.execute(delete(DeliveryRow).where(DeliveryRow.request_id == row.id))
        session.add(DeadLetterRow(request_id=row.id, code=code, created_at=now))
