from apps.projects.queries.projects import visible_project, visible_projects
from apps.sprints.models import Sprint
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
