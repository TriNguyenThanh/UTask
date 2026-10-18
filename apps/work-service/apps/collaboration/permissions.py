from uuid import UUID

from rest_framework.exceptions import NotFound

from apps.projects.models import Project, ProjectMember
from apps.projects.queries import visible_project
from apps.tasks.models import Task
from apps.tasks.queries import visible_task
from infrastructure.classroom import classroom_client
from infrastructure.identity import IdentityClient


def admin_feedback_access(actor, project):
    # Work owns this binding, verified against Classroom when the project was created.
    if not project.class_id or not project.classroom_group_id:
        return False
    token = getattr(actor, "access_token", "")
    if not token:
        return False
    user = IdentityClient().current_user(token)
    return UUID(user["id"]) == actor.id and "SYSTEM_ADMIN" in user["roles"]


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
    teacher = not member and project.classroom_group_id in classroom_client().teacher_group_ids(
        actor
    )
    if teacher and for_feedback:
        from common.errors import WorkError
        from infrastructure.collaboration_scope import VerifiedFeedbackScope

        verifier = getattr(classroom_client(), "teacher_feedback_scope", None)
        if verifier is None:
            raise WorkError(
                "CLASSROOM_UNAVAILABLE",
                "Chưa thể xác minh quyền gửi nhận xét của bạn.",
                503,
            )
        proof = verifier(project, actor)
        if not isinstance(proof, VerifiedFeedbackScope):
            raise WorkError(
                "CLASSROOM_UNAVAILABLE",
                "Chưa thể xác minh quyền gửi nhận xét của bạn.",
                503,
            )
        teacher = proof.validate(actor, project)
    return subject, project, teacher


def verified_teacher_mentions(actor, project, payload):
    from common.content import clean_content
    from common.errors import WorkError
    from infrastructure.classroom import classroom_client

    _, _, html_ids = clean_content(payload.get("content_html", ""))
    ids = html_ids | set(payload.get("mentioned_user_ids", []))
    member_ids = set(
        project.members.filter(user_id__in=ids, status="ACTIVE").values_list("user_id", flat=True)
    )
    other_ids = ids - member_ids
    if not other_ids:
        return frozenset()
    verifier = getattr(classroom_client(), "teacher_mention_ids", None)
    if verifier is None:
        raise WorkError(
            "CLASSROOM_UNAVAILABLE",
            "Chưa thể xác minh người được nhắc tên có quyền xem nội dung này.",
            503,
        )
    verified = frozenset(verifier(project.classroom_group_id, other_ids, actor))
    if verified != other_ids:
        raise WorkError(
            "VALIDATION_ERROR", "Người nhận thông báo không thuộc phạm vi của dự án.", 422
        )
    return verified
