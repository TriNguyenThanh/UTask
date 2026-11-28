"""Celery background tasks for Core Service outbox publishing and retention maintenance."""

from celery import shared_task

from apps.messaging.services.maintenance import cleanup_core_data
from apps.messaging.services.publisher import drain_outbox as run_drain_outbox


@shared_task(name="apps.messaging.tasks.drain_outbox")
def drain_outbox():
    return run_drain_outbox()


@shared_task(name="apps.messaging.tasks.cleanup_core_data")
def cleanup_core_data_task():
    return cleanup_core_data(apply=True)
