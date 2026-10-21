import logging

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from apps.integrations.models import GitHubConnectionOperation
from apps.integrations.services.operations import (
    MISSING_PREPARE,
    PENDING_STATES,
    cleanup_operations,
    recover_operation,
)

logger = logging.getLogger(__name__)


@shared_task
def recover_connections(operation_id=None):
    rows = GitHubConnectionOperation.objects.filter(
        Q(state="NEW")
        | Q(state__in=["CONFIRM", "ABORT"], attempts__lt=10)
        | Q(state="FAILED", last_error=MISSING_PREPARE),
        next_attempt_at__lte=timezone.now(),
    ).order_by("next_attempt_at", "pk")
    if operation_id:
        rows = GitHubConnectionOperation.objects.filter(
            Q(state__in=PENDING_STATES) | Q(state="FAILED", last_error=MISSING_PREPARE),
            pk=operation_id,
        )
    ids = list(rows.values_list("pk", flat=True)[:20])
    succeeded = 0
    for row_id in ids:
        try:
            succeeded += bool(recover_operation(row_id))
        except Exception as exc:
            from apps.integrations.services.operations import schedule_failure

            schedule_failure(row_id, exc)
            logger.warning(
                "GitHub connection recovery failed operation=%s error=%s",
                row_id,
                type(exc).__name__,
            )
    cleanup_operations()
    return {"processed": len(ids), "succeeded": succeeded}
