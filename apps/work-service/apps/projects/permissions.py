from rest_framework.exceptions import NotFound

from apps.projects.models import ProjectMember
from common.errors import WorkError


def active_member(project, actor):
    return ProjectMember.objects.filter(project=project, user_id=actor.id, status="ACTIVE").first()


def require_leader(project, actor, *, writable=True):
    member = active_member(project, actor)
    if member is None:
        raise NotFound("Không tìm thấy dự án yêu cầu.")
    if member.role != "LEADER":
        raise WorkError(
            "LEADER_PERMISSION_REQUIRED",
            "Chỉ trưởng nhóm mới có quyền thực hiện thao tác này.",
            403,
        )
    if project.deleted_at or (writable and project.archived_at):
        raise WorkError("INVALID_OPERATION", "Dự án đang ở chế độ chỉ đọc.")
    return member
