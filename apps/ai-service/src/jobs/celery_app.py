"""Redis chỉ là broker; result/status do PostgreSQL của AI giữ."""

from celery import Celery

from config import get_settings

settings = get_settings()
celery_app = Celery("utask_ai", broker=settings.broker_url, include=["jobs.tasks"])
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_cancel_long_running_tasks_on_connection_loss=True,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=3,
    broker_transport_options={
        "visibility_timeout": 60,
        "socket_timeout": 3,
        "socket_connect_timeout": 3,
    },
    task_soft_time_limit=35,
    task_time_limit=40,
    task_default_queue="utask_ai",
    task_publish_retry=False,
)
