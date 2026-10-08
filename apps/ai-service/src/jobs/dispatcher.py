"""Process dispatcher, scale được nhờ delivery lease trong PostgreSQL."""

import logging
import time
from uuid import UUID

from application.dispatch import RequestDispatcher
from config import get_settings
from infrastructure.bootstrap import build_repository

from .celery_app import celery_app


class CeleryPublisher:
    def publish(self, request_id: UUID):
        celery_app.send_task(
            "utask_ai.execute_request", args=[str(request_id)], task_id=str(request_id), retry=False
        )


def main():
    settings = get_settings()
    repository, engine = build_repository(settings)
    dispatcher = RequestDispatcher(repository, CeleryPublisher(), settings.max_dispatch_attempts)
    try:
        while True:
            try:
                dispatcher.dispatch_once()
            except Exception:
                logging.getLogger(__name__).error("Dispatcher tạm thời chưa thể giao job")
            time.sleep(settings.dispatch_interval_seconds)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
