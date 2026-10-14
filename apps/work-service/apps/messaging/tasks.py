from celery import shared_task

from apps.messaging.publisher import drain


@shared_task
def drain_outbox():
    return drain()
