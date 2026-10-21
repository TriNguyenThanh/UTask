"""Repository PostgreSQL; transaction và lock bảo vệ giao job/idempotency."""

import hashlib
import json
from datetime import datetime, timedelta
from math import ceil
from random import uniform
from uuid import UUID, uuid4

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import sessionmaker

from application.ports import Delivery, StoredRequest
from application.responses import failed_response
from errors import ServiceError, failure
from models import AiResponse, CreateAiRequest, QueuedAiResponse, RunningAiResponse
from models.validation import validate_result

from .db.tables import CompletionRow, DeadLetterRow, DeliveryRow, RequestRow

REQUEST_ADAPTER = TypeAdapter(CreateAiRequest)
RESPONSE_ADAPTER = TypeAdapter(AiResponse)
COMPLETION_CHANNEL = "utask_ai_completed"
# Hai-int advisory lock namespace dành riêng cho admission trong AI database.
ADMISSION_LOCK_NAMESPACE = 0x41495251


def admission_error(
    *,
    now: datetime,
    recent_count: int,
    oldest_recent: datetime | None,
    active_count: int,
    requests_per_minute: int,
    max_active_requests_per_user: int,
) -> ServiceError | None:
    """Quyết định admission; replay/conflict đã được xử lý trước bước này."""
    if recent_count >= requests_per_minute:
        retry_after = max(1, ceil((oldest_recent + timedelta(seconds=60) - now).total_seconds()))
        reason = "REQUEST_RATE_LIMIT"
    elif active_count >= max_active_requests_per_user:
        retry_after = 5
        reason = "ACTIVE_REQUEST_LIMIT"
    else:
        return None
    return ServiceError(
        "RATE_LIMITED",
        "Đã vượt giới hạn yêu cầu AI. Vui lòng thử lại sau.",
        429,
        retryable=True,
        details={"reason": reason, "retry_after_seconds": retry_after},
    )


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
        requests_per_minute: int = 5,
        max_active_requests_per_user: int = 2,
    ):
        if requests_per_minute < 1 or max_active_requests_per_user < 1:
            raise ValueError("Giới hạn admission phải dương")
        self.sessions = sessions
        self.queue_timeout = queue_timeout
        self.workflow_timeout = workflow_timeout
        self.dispatch_lease = dispatch_lease
        self.redelivery = redelivery
        self.max_dispatch_attempts = max_dispatch_attempts
        self.requests_per_minute = requests_per_minute
        self.max_active_requests_per_user = max_active_requests_per_user

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
        payload_fingerprint = fingerprint(payload)
        with self.sessions.begin() as session:
            # Hash ổn định giữa process; collision chỉ làm hai user chờ nhau.
            lock_key = int.from_bytes(hashlib.sha256(user_id.encode()).digest()[:4], signed=True)
            session.execute(
                text("SELECT pg_advisory_xact_lock(:namespace, :user_key)"),
                {"namespace": ADMISSION_LOCK_NAMESPACE, "user_key": lock_key},
            )
            existing = session.scalars(
                select(RequestRow).where(
                    RequestRow.user_id == user_id, RequestRow.idempotency_key == key
                )
            ).one_or_none()
            if existing is not None:
                if existing.fingerprint != payload_fingerprint:
                    raise failure("IDEMPOTENCY_CONFLICT", 409)
                return record(existing)
            recent_count, oldest_recent = session.execute(
                select(func.count(), func.min(RequestRow.created_at)).where(
                    RequestRow.user_id == user_id,
                    RequestRow.created_at > now - timedelta(seconds=60),
                )
            ).one()
            active_count = session.scalar(
                select(func.count())
                .select_from(RequestRow)
                .where(
                    RequestRow.user_id == user_id,
                    RequestRow.status.in_(("queued", "running")),
                )
            )
            error = admission_error(
                now=now,
                recent_count=recent_count,
                oldest_recent=oldest_recent,
                active_count=active_count,
                requests_per_minute=self.requests_per_minute,
                max_active_requests_per_user=self.max_active_requests_per_user,
            )
            if error:
                raise error
            created = session.execute(
                insert(RequestRow)
                .values(
                    id=request_id,
                    user_id=user_id,
                    idempotency_key=key,
                    fingerprint=payload_fingerprint,
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
            if row.fingerprint != payload_fingerprint:
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

    def stage_completion(
        self, request_id: UUID, token: UUID, response: AiResponse, now: datetime
    ) -> bool:
        """Bàn giao bền vững và NOTIFY sau commit; chưa cập nhật terminal state."""
        if response.status not in {"succeeded", "failed"} or response.request_id != request_id:
            raise ValueError("Chỉ bàn giao kết quả cuối cùng của chính request")
        with self.sessions.begin() as session:
            row = session.scalars(
                select(RequestRow).where(RequestRow.id == request_id).with_for_update()
            ).one_or_none()
            if row is None or row.status != "running" or row.execution_token != token:
                return False
            # Lần bàn giao đầu tiên là kết quả duy nhất; retry không thay nội dung.
            if session.get(CompletionRow, request_id) is None:
                if row.execution_deadline <= now:
                    response = failed_response(
                        REQUEST_ADAPTER.validate_python(row.payload),
                        row.id,
                        row.created_at,
                        now,
                        failure("WORKFLOW_TIMEOUT", 504),
                    )
                session.add(
                    CompletionRow(
                        request_id=request_id,
                        execution_token=token,
                        response=response.model_dump(mode="json"),
                        created_at=now,
                    )
                )
                # Sau bàn giao không còn dùng Bearer, kể cả khi API tạm dừng.
                row.credential = ""
            session.execute(
                text("SELECT pg_notify(:channel, :request_id)"),
                {"channel": COMPLETION_CHANNEL, "request_id": str(request_id)},
            )
            return True

    def accept_completions(self, limit: int = 100) -> int:
        """API apply inbox + xóa inbox cùng transaction; nhiều API không ghi trùng."""
        if limit < 1:
            raise ValueError("Batch completion phải dương")
        with self.sessions.begin() as session:
            rows = session.scalars(
                select(RequestRow)
                .join(CompletionRow, CompletionRow.request_id == RequestRow.id)
                .order_by(CompletionRow.created_at, CompletionRow.request_id)
                .limit(limit)
                .with_for_update(of=RequestRow, skip_locked=True)
            ).all()
            for row in rows:
                completion = session.get(CompletionRow, row.id)
                if row.status == "running" and row.execution_token == completion.execution_token:
                    try:
                        response = RESPONSE_ADAPTER.validate_python(completion.response)
                        payload = REQUEST_ADAPTER.validate_python(row.payload)
                        if (
                            response.status not in {"succeeded", "failed"}
                            or response.request_id != row.id
                            or response.intent != payload.intent
                            or response.output_schema_version != payload.output_schema_version
                        ):
                            raise ValueError("Completion không khớp request")
                        if response.status == "succeeded":
                            validate_result(payload.intent, response.result)
                            if completion.created_at >= row.execution_deadline:
                                raise ValueError("Success bàn giao quá deadline")
                    except (ValidationError, ValueError):
                        self._fail(session, row, "OUTPUT_VALIDATION_FAILED", completion.created_at)
                    else:
                        row.status = response.status
                        row.terminal_at = completion.created_at
                        row.response = response.model_dump(mode="json")
                        row.credential = ""
                        row.execution_token = None
                        if response.status == "failed":
                            session.add(
                                DeadLetterRow(
                                    request_id=row.id,
                                    code=response.error.code,
                                    created_at=completion.created_at,
                                )
                            )
                session.delete(completion)
            return len(rows)

    def cleanup_terminal(self, now: datetime, *, retention_days: int = 30, limit: int = 500) -> int:
        """Xóa một batch terminal; khóa cha và cascade con trong transaction ngắn."""
        if retention_days < 1 or not 1 <= limit <= 500:
            raise ValueError("Retention phải dương và batch nằm trong 1..500")
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Thời điểm retention phải có múi giờ")
        cutoff = now - timedelta(days=retention_days)
        with self.sessions.begin() as session:
            ids = session.scalars(
                select(RequestRow.id)
                .where(
                    RequestRow.status.in_(("succeeded", "failed")),
                    RequestRow.terminal_at < cutoff,
                )
                .order_by(RequestRow.terminal_at, RequestRow.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
            if not ids:
                return 0
            session.execute(delete(RequestRow).where(RequestRow.id.in_(ids)))
            return len(ids)

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
                .where(
                    ~select(CompletionRow.request_id)
                    .where(CompletionRow.request_id == RequestRow.id)
                    .exists()
                )
                .with_for_update(skip_locked=True)
            ).all()
            expired = 0
            for row in rows:
                # Recheck sau khi khóa: completion có thể commit trong lúc scan.
                if session.get(CompletionRow, row.id) is not None:
                    continue
                self._fail(
                    session,
                    row,
                    "QUEUE_TIMEOUT" if row.status == "queued" else "WORKFLOW_TIMEOUT",
                    now,
                )
                expired += 1
            return expired

    def _fail(self, session, row: RequestRow, code: str, now: datetime) -> None:
        if row.status in {"succeeded", "failed"}:
            return
        response = failed_response(
            REQUEST_ADAPTER.validate_python(row.payload), row.id, row.created_at, now, failure(code)
        )
        row.response = response.model_dump(mode="json")
        row.status = "failed"
        row.terminal_at = now
        row.credential = ""
        row.execution_token = None
        session.execute(delete(DeliveryRow).where(DeliveryRow.request_id == row.id))
        session.add(DeadLetterRow(request_id=row.id, code=code, created_at=now))
