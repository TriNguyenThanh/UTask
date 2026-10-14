from django.db import transaction
from django.utils import timezone

from apps.projects.metrics import FORMULA_VERSION, metric_totals
from apps.projects.permissions import active_member
from apps.projects.queries.projects import read_project_scope, visible_project, visible_projects
from apps.projects.services.locking import lock_project
from apps.sprints.models import Sprint, SprintTask
from apps.sprints.queries.history import BUSINESS_ZONE, burndown_history
from apps.tasks.models import Task
from common.errors import WorkError
from common.pagination import paginate
from infrastructure.classroom import classroom_client


def sprint_list(actor, project_id, params):
    project = visible_project(actor, project_id)
    status = params.get("status")
    rows = Sprint.objects.filter(project=project, archived_at__isnull=True)
    if status:
        if status not in Sprint.Status.values:
            raise WorkError("VALIDATION_ERROR", "Trạng thái chu kỳ làm việc không hợp lệ.")
        rows = rows.filter(status=status)
    return paginate(
        rows,
        params,
        scope={"actor": str(actor.id), "project_id": str(project_id), "status": status},
    )


def visible_sprint(actor, sprint_id, *, for_write=False):
    from rest_framework.exceptions import NotFound

    # Membership can authorize a read without Classroom. Otherwise obtain Teacher
    # scope before resolving the ID, including unknown IDs; outages remain fail-closed.
    sprint = Sprint.objects.filter(
        pk=sprint_id,
        project__deleted_at__isnull=True,
        project__members__user_id=actor.id,
        project__members__status="ACTIVE",
    ).first()
    teacher_proven = sprint is None
    if teacher_proven:
        groups = classroom_client().teacher_group_ids(actor)
        sprint = Sprint.objects.filter(
            pk=sprint_id, project__in=visible_projects(actor, teacher_groups=groups)
        ).first()
    if sprint is None:
        raise NotFound("Không tìm thấy chu kỳ làm việc yêu cầu.")
    if for_write and teacher_proven:
        raise WorkError(
            "TEACHER_MUTATION_RESTRICTED",
            "Giảng viên chỉ có quyền xem nội dung hoặc gửi nhận xét.",
            403,
        )
    return sprint


def scope_read(actor, sprint_id, *, burndown=False):
    sprint = visible_sprint(actor, sprint_id)
    _, teacher_proven = read_project_scope(actor, sprint.project_id)
    with transaction.atomic():
        project = lock_project(sprint.project_id)
        if active_member(project, actor) is None and not teacher_proven:
            from rest_framework.exceptions import NotFound

            raise NotFound("Không tìm thấy chu kỳ làm việc yêu cầu.")
        sprint.refresh_from_db()
        now = timezone.now()
        if sprint.status == "COMPLETED":
            snapshot = sprint.closure_snapshot
            if burndown:
                return {
                    "sprint_id": str(sprint.pk),
                    "captured_at": snapshot["captured_at"],
                    "snapshot_version": snapshot["snapshot_version"],
                    **snapshot["daily_burndown"],
                }
            return {
                "sprint_id": str(sprint.pk),
                "captured_at": snapshot["captured_at"],
                "snapshot_version": snapshot["snapshot_version"],
                "formula_version": snapshot["formula_version"],
                "totals": snapshot["totals"],
            }
        if burndown:
            return {
                "sprint_id": str(sprint.pk),
                "captured_at": now,
                "snapshot_version": None,
                **burndown_history(sprint, now),
            }
        ids = SprintTask.objects.filter(
            sprint=sprint, ended_at__isnull=True, deleted_at__isnull=True
        ).values("task_id")
        queryset = Task.objects.filter(
            pk__in=ids, deleted_at__isnull=True, archived_at__isnull=True
        )
        return {
            "sprint_id": str(sprint.pk),
            "captured_at": now,
            "snapshot_version": None,
            "formula_version": FORMULA_VERSION,
            "totals": metric_totals(queryset, now.astimezone(BUSINESS_ZONE).date()),
        }
