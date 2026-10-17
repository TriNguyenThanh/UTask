import logging

from celery import shared_task
from django.db import OperationalError

from apps.projects.models import Project
from apps.projects.services.membership import synchronize_membership
from common.errors import WorkError
from infrastructure.classroom import classroom_client

logger = logging.getLogger(__name__)


@shared_task(autoretry_for=(WorkError, OperationalError), retry_backoff=True, max_retries=5)
def recover_project_membership(project_id):
    project = Project.objects.filter(
        pk=project_id, archived_at__isnull=True, deleted_at__isnull=True
    ).first()
    if project is None:
        return False
    client = classroom_client()
    # Local developer adapters have no remote recovery authority.
    read_snapshot = getattr(client, "recovery_snapshot", None)
    if read_snapshot is None:
        return False
    snapshot = read_snapshot(project.classroom_group_id)
    return synchronize_membership(project.pk, snapshot)


@shared_task
def recover_active_memberships():
    """Periodic repair also covers a crash or broker failure after the create commit."""
    failures = 0
    projects = (
        Project.objects.filter(archived_at__isnull=True, deleted_at__isnull=True)
        .order_by("id")
        .values_list("id", flat=True)
    )
    for project_id in projects.iterator(chunk_size=100):
        try:
            recover_project_membership.run(str(project_id))
        except Exception as exc:
            failures += 1
            logger.warning(
                "Membership recovery failed project=%s error=%s", project_id, type(exc).__name__
            )
    return {"failed": failures}
