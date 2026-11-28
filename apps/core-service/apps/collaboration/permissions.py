from rest_framework.exceptions import NotFound

from apps.accounts.interface import has_global_role
from apps.groups.interface import (
    get_teacher_group_ids,
    get_teacher_mention_ids,
    verify_feedback_scope,
)
from apps.projects.models import Project, ProjectMember
from apps.projects.queries import visible_project
from apps.tasks.models import Task
from apps.tasks.queries import visible_task
from common.content import clean_content
from common.errors import CoreAPIError


def admin_feedback_access(actor, project):
    # Work owns this binding, verified against Classroom when the project was created.
    if not project.class_id or not project.classroom_group_id:
        return False
    return has_global_role(actor.id, "SYSTEM_ADMIN")


def subject_access(actor, *, task_id=None, project_id=None, for_feedback=False):
    try:
        subject = visible_task(actor, task_id) if task_id else visible_project(actor, project_id)
    except NotFound:
        if not for_feedback:
            raise
        subject = (
            Task.objects.select_related("project")
            .filter(pk=task_id, deleted_at__isnull=True, project__deleted_at__isnull=True)
            .first()
            if task_id
            else Project.objects.filter(pk=project_id, deleted_at__isnull=True).first()
        )
        project = subject.project if subject and task_id else subject
        if project is None or not admin_feedback_access(actor, project):
            raise NotFound("Không tìm thấy đối tượng bình luận yêu cầu.") from None
        return subject, project, False
    project = subject.project if task_id else subject
    member = ProjectMember.objects.filter(
        project=project, user_id=actor.id, status="ACTIVE"
    ).exists()
    teacher = not member and project.classroom_group_id in get_teacher_group_ids(actor)
    if teacher and for_feedback:
        teacher = verify_feedback_scope(project, actor)
    return subject, project, teacher


def verified_teacher_mentions(actor, project, payload):
    _, _, html_ids = clean_content(payload.get("content_html", ""))
    ids = html_ids | set(payload.get("mentioned_user_ids", []))
    member_ids = set(
        project.members.filter(user_id__in=ids, status="ACTIVE").values_list("user_id", flat=True)
    )
    other_ids = ids - member_ids
    if not other_ids:
        return frozenset()
    verified = get_teacher_mention_ids(project.classroom_group_id, other_ids, actor)
    if verified != other_ids:
        raise CoreAPIError(
            "VALIDATION_ERROR", "Người nhận thông báo không thuộc phạm vi của dự án.", 422
        )
    return verified
