from apps.projects.models import ProjectMember
from apps.projects.queries import visible_project
from apps.tasks.queries import visible_task
from infrastructure.classroom import classroom_client


def subject_access(actor, *, task_id=None, project_id=None, for_feedback=False):
    subject = visible_task(actor, task_id) if task_id else visible_project(actor, project_id)
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
