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
        "visibility_timeout": int(settings.workflow_timeout_seconds) + 30,
        "socket_timeout": 3,
        "socket_connect_timeout": 3,
    },
    task_soft_time_limit=settings.workflow_timeout_seconds + 5,
    task_time_limit=settings.workflow_timeout_seconds + 10,
    task_default_queue="utask_ai",
    task_publish_retry=False,
    beat_schedule={
        "ai-terminal-retention": {
            "task": "utask_ai.cleanup_terminal",
            "schedule": settings.retention_interval_seconds,
            "options": {"queue": "utask_ai", "expires": settings.retention_interval_seconds},
        }
    },
)
