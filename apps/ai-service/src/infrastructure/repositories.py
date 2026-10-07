"""Adapter lưu yêu cầu AI trong memory cho bootstrap local."""

from uuid import UUID

from application.ports import StoredRequest


class InMemoryRequestRepository:
    """Development repository; replace with ai_context_db persistence before staging."""

    def __init__(self) -> None:
        self._records: dict[UUID, StoredRequest] = {}

    def get(self, request_id: UUID) -> StoredRequest | None:
        return self._records.get(request_id)

    def find_by_idempotency(
        self, requester_user_id: str, idempotency_key: str
    ) -> StoredRequest | None:
        return next(
            (
                record
                for record in self._records.values()
                if record.requester_user_id == requester_user_id
                and record.idempotency_key == idempotency_key
            ),
            None,
        )

    def save(self, record: StoredRequest) -> None:
        self._records[record.response.request_id] = record
