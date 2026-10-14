from django.db.models import OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from rest_framework.exceptions import NotFound

from apps.collaboration.models import Attachment, Comment
from apps.collaboration.permissions import subject_access
from apps.messaging.models import Activity
from apps.projects.models import ProjectMember, UserProjection
from infrastructure.classroom import classroom_client


def comment_queryset():
    profiles = UserProjection.objects.filter(user_id=OuterRef("user_id"))
    return (
        Comment.objects.select_related("project", "task__project")
        .prefetch_related("mentions")
        .annotate(
            display_name=Coalesce(Subquery(profiles.values("display_name")[:1]), Value("")),
            avatar_url=Subquery(profiles.values("avatar_url")[:1]),
        )
    )


def visible_comment(actor, comment_id):
    scope = ProjectMember.objects.filter(user_id=actor.id, status="ACTIVE").values("project_id")
    query = comment_queryset().filter(deleted_at__isnull=True)
    member = query.filter(
        Q(project_id__in=scope) | Q(task__project_id__in=scope), pk=comment_id
    ).first()
    if member:
        subject_access(actor, task_id=member.task_id, project_id=member.project_id)
        return member
    groups = classroom_client().teacher_group_ids(actor)
    comment = query.filter(
        Q(project__classroom_group_id__in=groups) | Q(task__project__classroom_group_id__in=groups),
        pk=comment_id,
    ).first()
    if comment is None:
        raise NotFound("Không tìm thấy bình luận yêu cầu.")
    subject_access(actor, task_id=comment.task_id, project_id=comment.project_id)
    return comment


def subject_comments(*, task_id=None, project_id=None):
    return comment_queryset().filter(
        task_id=task_id, project_id=project_id, deleted_at__isnull=True
    )


def subject_attachments(*, task_id=None, project_id=None):
    return Attachment.objects.filter(
        task_id=task_id, project_id=project_id, status="CONFIRMED", deleted_at__isnull=True
    )


def task_activities(task_id):
    return Activity.objects.filter(Q(task_id=task_id) | Q(comment__task_id=task_id))
