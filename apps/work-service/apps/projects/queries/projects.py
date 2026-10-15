import logging

from django.db.models import Exists, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from rest_framework.exceptions import NotFound

from apps.projects.models import Project, ProjectMember, UserProjection
from common.errors import WorkError
from common.pagination import paginate
from infrastructure.classroom import classroom_client

logger = logging.getLogger(__name__)


def project_list(actor, params):
    status = params.get("status", "active")
    if status not in {"active", "archived", "all"}:
        raise WorkError("VALIDATION_ERROR", "Trạng thái dự án không hợp lệ.")
    group_id = params.get("classroom_group_id")
    partial = False
    try:
        teacher_groups = classroom_client().teacher_group_ids(actor)
    except WorkError as exc:
        if exc.code != "CLASSROOM_UNAVAILABLE" or group_id:
            raise
        teacher_groups = []
        partial = True
        logger.warning("Project list limited to Work membership code=CLASSROOM_UNAVAILABLE")
    queryset = visible_projects(actor, teacher_groups=teacher_groups)
    if status != "all":
        queryset = queryset.filter(archived_at__isnull=status == "active")
    if group_id:
        if group_id not in teacher_groups:
            raise WorkError(
                "PERMISSION_DENIED",
                "Bạn không có quyền giảng viên đối với nhóm học tập này.",
                403,
            )
        queryset = queryset.filter(classroom_group_id=group_id)
    rows, meta = paginate(
        queryset,
        params,
        scope={
            "actor": str(actor.id),
            "status": status,
            "group": group_id,
            "teacher_groups": sorted(teacher_groups),
            "partial": partial,
        },
    )
    if partial:
        meta["scope"] = {
            "partial": True,
            "source": "WORK_MEMBERSHIP",
            "teacher_scope": "UNAVAILABLE",
        }
    return rows, meta


def state_list(actor, project_id):
    project = visible_project(actor, project_id)
    return list(project.states.filter(deleted_at__isnull=True).order_by("sequence", "id"))


def visible_projects(actor, *, teacher_groups=None):
    member = ProjectMember.objects.filter(
        project_id=OuterRef("pk"), user_id=actor.id, status="ACTIVE"
    )
    # Identity tokens have no role claims. Teacher scope always comes from Classroom.
    if teacher_groups is None:
        teacher_groups = classroom_client().teacher_group_ids(actor)
    return (
        Project.objects.filter(deleted_at__isnull=True)
        .annotate(is_member=Exists(member))
        .filter(Q(is_member=True) | Q(classroom_group_id__in=teacher_groups))
    )


def read_project_scope(actor, project_id):
    project = Project.objects.filter(pk=project_id, deleted_at__isnull=True).first()
    if project is None:
        raise NotFound("Không tìm thấy dự án yêu cầu.")
    if ProjectMember.objects.filter(project=project, user_id=actor.id, status="ACTIVE").exists():
        return project, False
    if project.classroom_group_id not in classroom_client().teacher_group_ids(actor):
        raise NotFound("Không tìm thấy dự án yêu cầu.")
    return project, True


def visible_project(actor, project_id, *, for_write=False):
    project, teacher_proven = read_project_scope(actor, project_id)
    if for_write and teacher_proven:
        raise WorkError(
            "TEACHER_MUTATION_RESTRICTED",
            "Giảng viên chỉ có quyền xem nội dung hoặc gửi nhận xét.",
            403,
        )
    return project


def member_queryset(project, status="ACTIVE"):
    if status not in {"ACTIVE", "LEFT", "REMOVED", "all"}:
        raise WorkError("VALIDATION_ERROR", "Trạng thái thành viên không hợp lệ.")
    profile = UserProjection.objects.filter(user_id=OuterRef("user_id"))
    queryset = ProjectMember.objects.filter(project=project).annotate(
        display_name=Coalesce(Subquery(profile.values("display_name")[:1]), Value("")),
        avatar_url=Subquery(profile.values("avatar_url")[:1]),
    )
    return queryset if status == "all" else queryset.filter(status=status)
