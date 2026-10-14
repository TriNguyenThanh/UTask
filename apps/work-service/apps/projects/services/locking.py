from django.db import connection
from rest_framework.exceptions import NotFound

from apps.projects.models import Project


def lock_project(project_id):
    if not connection.in_atomic_block:
        raise RuntimeError("Project barrier requires transaction.atomic")
    try:
        return Project.objects.select_for_update().get(pk=project_id, deleted_at__isnull=True)
    except Project.DoesNotExist as exc:
        raise NotFound("Không tìm thấy dự án yêu cầu.") from exc
