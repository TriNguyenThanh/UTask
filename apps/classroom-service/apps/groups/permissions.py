from apps.courses.models import Enrollment
from apps.courses.permissions import is_teacher
from apps.groups.models import GroupMember
from common.errors import ClassroomError


def active_enrollment(section, actor):
    enrollment = Enrollment.objects.filter(
        class_section=section, user_id=actor.id, status="ACTIVE"
    ).first()
    if enrollment is None:
        raise ClassroomError("ENROLLMENT_REQUIRED", "Bạn cần đang tham gia lớp học này.", 403)
    return enrollment


def active_member(group, actor):
    return GroupMember.objects.filter(
        group=group, enrollment__user_id=actor.id, enrollment__status="ACTIVE", status="ACTIVE"
    ).first()


def require_group_read(group, actor):
    if not active_member(group, actor) and not is_teacher(actor, group.class_section):
        raise ClassroomError("RESOURCE_NOT_FOUND", "Không tìm thấy nhóm học tập.", 404)


def require_leader(group, actor, *, teacher_allowed=False):
    member = active_member(group, actor)
    if not (member and member.role == "LEADER") and not (
        teacher_allowed and is_teacher(actor, group.class_section)
    ):
        raise ClassroomError(
            "LEADER_PERMISSION_REQUIRED",
            (
                "Chỉ trưởng nhóm hoặc giảng viên phụ trách mới được thực hiện thao tác này."
                if teacher_allowed
                else "Chỉ trưởng nhóm mới được thực hiện thao tác này."
            ),
            403,
        )
