from celery import shared_task


@shared_task(ignore_result=True)
def publish_connection_events():
    from .publisher import publish_outbox

    return publish_outbox()


@shared_task(ignore_result=True)
def expire_connection_operations():
    from .services import expire_operations

    return expire_operations()


@shared_task(ignore_result=True)
def cleanup_connection_events():
    from .outbox import cleanup_outbox

    return cleanup_outbox()
