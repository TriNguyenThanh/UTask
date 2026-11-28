import logging
from contextlib import contextmanager

from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from rest_framework.exceptions import NotFound

from apps.accounts.interface import get_user_profiles
from apps.groups.interface import get_teacher_group_ids
from apps.projects.models import Project, ProjectMember
from apps.projects.permissions import active_member
from apps.projects.services.locking import lock_project
from common.errors import CoreAPIError
from common.pagination import paginate

logger = logging.getLogger(__name__)


def extract_profile(profiles: dict, user_id) -> tuple[str, str | None]:
    """Return (display_name, avatar_url) from a profile lookup mapping."""
    if not profiles or user_id is None:
        return "", None
    profile = profiles.get(user_id)
    if profile is None:
        profile = profiles.get(str(user_id))
    if profile is None:
        return "", None
    if isinstance(profile, dict):
        return profile.get("display_name") or "", profile.get("avatar_url")
    return getattr(profile, "display_name", "") or "", getattr(profile, "avatar_url", None)


def _teacher_groups(actor) -> list[str]:
    return [str(group_id) for group_id in get_teacher_group_ids(actor)]


def project_list(actor, params):
    status = params.get("status", "active")
    if status not in {"active", "archived", "all"}:
        raise CoreAPIError("VALIDATION_ERROR", "Trạng thái dự án không hợp lệ.")
    group_id = params.get("classroom_group_id")
    partial = False
    try:
        teacher_groups = _teacher_groups(actor)
    except CoreAPIError as exc:
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
            raise CoreAPIError(
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
    if teacher_groups is None:
        teacher_groups = _teacher_groups(actor)
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
    if project.classroom_group_id not in _teacher_groups(actor):
        raise NotFound("Không tìm thấy dự án yêu cầu.")
    return project, True


def visible_project(actor, project_id, *, for_write=False):
    project, teacher_proven = read_project_scope(actor, project_id)
    if for_write and teacher_proven:
        raise CoreAPIError(
            "TEACHER_MUTATION_RESTRICTED",
            "Giảng viên chỉ có quyền xem nội dung hoặc gửi nhận xét.",
            403,
        )
    return project


@contextmanager
def readable_project(actor, project_id):
    """Verify Teacher scope outside the transaction, then recheck under the Project barrier."""
    proof, teacher = read_project_scope(actor, project_id)
    with transaction.atomic():
        project = lock_project(project_id)
        if active_member(project, actor) is None and not (
            teacher and project.classroom_group_id == proof.classroom_group_id
        ):
            raise NotFound("Không tìm thấy nội dung yêu cầu.")
        yield project


def member_queryset(project, status="ACTIVE"):
    if status not in {"ACTIVE", "LEFT", "REMOVED", "all"}:
        raise CoreAPIError("VALIDATION_ERROR", "Trạng thái thành viên không hợp lệ.")
    queryset = ProjectMember.objects.filter(project=project)
    return queryset if status == "all" else queryset.filter(status=status)


def hydrate_member_profiles(members):
    rows = list(members)
    if not rows:
        return rows
    user_ids = {row.user_id for row in rows}
    profiles = get_user_profiles(user_ids)
    for row in rows:
        display_name, avatar_url = extract_profile(profiles, row.user_id)
        row.display_name = display_name
        row.avatar_url = avatar_url
    return rows
