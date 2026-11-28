"""Public in-process interface for the Work Projects domain."""

from uuid import UUID

from apps.projects.models import Project
from apps.projects.services.membership import synchronize_membership


def sync_group_membership(group_id: UUID | str, snapshot) -> int:
    """Synchronize Classroom group membership across all active non-deleted projects."""
    try:
        group_key = str(UUID(str(group_id)))
    except (ValueError, TypeError, AttributeError):
        group_key = str(group_id)
    project_ids = list(
        Project.objects.filter(
            classroom_group_id=group_key,
            deleted_at__isnull=True,
            archived_at__isnull=True,
        )
        .order_by("id")
        .values_list("id", flat=True)
    )
    synced = 0
    for project_id in project_ids:
        if synchronize_membership(project_id, snapshot):
            synced += 1
    return synced
