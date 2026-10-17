from django.db import IntegrityError, transaction

from apps.courses.models import ClassSection
from apps.courses.permissions import require_open
from apps.groups.models import GroupProjectLink, StudyGroup
from apps.messaging.services.audit import record_activity
from common.errors import ClassroomError


def link_project(project_id, class_id, group_id):
    with transaction.atomic():
        section = ClassSection.objects.select_for_update().filter(pk=class_id).first()
        if section is None:
            raise ClassroomError("RESOURCE_NOT_FOUND", "Không tìm thấy lớp học.", 404)
        existing = GroupProjectLink.objects.filter(project_id=project_id).first()
        if existing:
            if existing.class_section_id != class_id or existing.group_id != group_id:
                raise ClassroomError(
                    "PROJECT_LINK_CONFLICT", "Dự án đã liên kết với nhóm khác.", 409
                )
            return False
        require_open(section)
        group = (
            StudyGroup.objects.select_for_update()
            .filter(pk=group_id, class_section=section, status="ACTIVE")
            .first()
        )
        if group is None:
            raise ClassroomError(
                "RESOURCE_NOT_FOUND", "Không tìm thấy nhóm đang hoạt động trong lớp học.", 404
            )
        try:
            with transaction.atomic():
                link = GroupProjectLink.objects.create(
                    class_section=section, group=group, project_id=project_id
                )
        except IntegrityError as exc:
            if (
                getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None)
                != "uq_group_project_project"
            ):
                raise
            existing = GroupProjectLink.objects.get(project_id=project_id)
            if existing.class_section_id != class_id or existing.group_id != group_id:
                raise ClassroomError(
                    "PROJECT_LINK_CONFLICT", "Dự án đã liên kết với nhóm khác.", 409
                ) from exc
            return False
        record_activity(
            link, None, "project.linked", new={"project_id": project_id, "group_id": group_id}
        )
        return True
