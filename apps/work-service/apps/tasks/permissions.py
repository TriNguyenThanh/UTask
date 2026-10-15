from rest_framework.exceptions import NotFound

from apps.projects.permissions import active_member
from common.errors import WorkError


def require_task_writer(
    project, actor, task=None, *, leader_only=False, archived=False, deleted=False
):
    member = active_member(project, actor)
    if member is None:
        raise NotFound("Không tìm thấy công việc yêu cầu.")
    if member.role != "LEADER" and (
        leader_only or task is None or not task.assignments.filter(user_id=actor.id).exists()
    ):
        raise WorkError(
            "LEADER_PERMISSION_REQUIRED" if leader_only else "PERMISSION_DENIED",
            "Không có quyền thực hiện thao tác này.",
            403,
        )
    if (
        project.archived_at
        or project.deleted_at
        or (task and ((task.archived_at and not archived) or (task.deleted_at and not deleted)))
    ):
        raise WorkError("INVALID_OPERATION", "Tài nguyên đang ở chế độ chỉ đọc.")
    return member


def require_member_fields(member, payload, allowed):
    if member.role != "LEADER" and set(payload) - set(allowed):
        raise WorkError(
            "LEADER_PERMISSION_REQUIRED",
            "Các trường điều phối chỉ dành riêng cho trưởng nhóm.",
            403,
            [
                {"field": field, "issue": "Không có quyền sửa trường này."}
                for field in sorted(set(payload) - set(allowed))
            ],
        )
