"""Giao job bền vững; lỗi broker không gọi lại workflow."""

from datetime import UTC, datetime

from .ports import JobPublisher, RequestRepository


class RequestDispatcher:
    def __init__(
        self, repository: RequestRepository, publisher: JobPublisher, max_attempts: int = 8
    ):
        self.repository = repository
        self.publisher = publisher
        self.max_attempts = max_attempts

    def dispatch_once(self) -> int:
        self.repository.expire(datetime.now(UTC))
        deliveries = self.repository.deliveries(datetime.now(UTC))
        for delivery in deliveries:
            if delivery.attempts > self.max_attempts:
                self.repository.delivery_failed(delivery, datetime.now(UTC))
                continue
            try:
                self.publisher.publish(delivery.request_id)
            except Exception:
                self.repository.delivery_failed(delivery, datetime.now(UTC))
            else:
                self.repository.delivered(delivery, datetime.now(UTC))
        return len(deliveries)
