from django.db.models import OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from rest_framework.exceptions import NotFound

from apps.collaboration.models import Attachment, Comment
from apps.collaboration.permissions import subject_access
from apps.messaging.models import Activity
from apps.projects.models import ProjectMember, UserProjection
from apps.projects.queries.projects import readable_project
from common.pagination import paginate
from infrastructure.classroom import classroom_client

SUBJECT_FIELD_MAP = (
    ("PROJECT", "project_id"),
    ("PROJECT_MEMBER", "project_member_id"),
    ("STATE", "state_id"),
    ("TASK", "task_id"),
    ("EPIC", "epic_id"),
    ("LABEL", "label_id"),
    ("COMMENT", "comment_id"),
    ("SPRINT", "sprint_id"),
)
SUBJECT_FIELD_BY_TYPE = dict(SUBJECT_FIELD_MAP)


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


def visible_comment(actor, comment_id, *, for_feedback=False):
    scope = ProjectMember.objects.filter(user_id=actor.id, status="ACTIVE").values("project_id")
    query = comment_queryset().filter(deleted_at__isnull=True)
    if for_feedback:
        own = query.filter(pk=comment_id, user_id=actor.id).first()
        if own:
            subject_access(actor, task_id=own.task_id, project_id=own.project_id, for_feedback=True)
            return own
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


def subject_comments(*, task_id=None, project_id=None, is_teacher_feedback=None):
    queryset = comment_queryset().filter(
        task_id=task_id, project_id=project_id, deleted_at__isnull=True
    )
    if is_teacher_feedback is not None:
        queryset = queryset.filter(is_teacher_feedback=is_teacher_feedback)
    return queryset


def subject_attachments(*, task_id=None, project_id=None):
    return Attachment.objects.filter(
        task_id=task_id, project_id=project_id, status="CONFIRMED", deleted_at__isnull=True
    )


def task_activities(task_id):
    return Activity.objects.filter(Q(task_id=task_id) | Q(comment__task_id=task_id))


def _activity_subject(activity):
    for subject_type, attr in SUBJECT_FIELD_MAP:
        subject_id = getattr(activity, attr)
        if subject_id is not None:
            return subject_type, str(subject_id)
    return "PROJECT", str(activity.scope_project_id) if activity.scope_project_id else None


def project_activities(actor, project_id, filters, query_params):
    with readable_project(actor, project_id) as project:
        queryset = Activity.objects.filter(scope_project_id=project.pk)
        if "subject_type" in filters:
            field_name = SUBJECT_FIELD_BY_TYPE[filters["subject_type"]]
            queryset = queryset.filter(**{f"{field_name}__isnull": False})
        if "verb" in filters:
            queryset = queryset.filter(verb=filters["verb"])
        if "actor_user_id" in filters:
            queryset = queryset.filter(actor_user_id=filters["actor_user_id"])
        if "created_from" in filters:
            queryset = queryset.filter(created_at__gte=filters["created_from"])
        if "created_to" in filters:
            queryset = queryset.filter(created_at__lte=filters["created_to"])
        rows, meta = paginate(
            queryset,
            query_params,
            scope={
                "actor": str(actor.id),
                "project": str(project.pk),
                "resource": "project_activities",
                "subject_type": filters.get("subject_type"),
                "verb": filters.get("verb"),
                "actor_user_id": (
                    str(filters["actor_user_id"]) if "actor_user_id" in filters else None
                ),
                "created_from": (
                    filters["created_from"].isoformat() if "created_from" in filters else None
                ),
                "created_to": (
                    filters["created_to"].isoformat() if "created_to" in filters else None
                ),
            },
        )
        actor_ids = {row.actor_user_id for row in rows if row.actor_user_id is not None}
        profiles = UserProjection.objects.in_bulk(actor_ids) if actor_ids else {}
        items = []
        for row in rows:
            subject_type, subject_id = _activity_subject(row)
            profile = profiles.get(row.actor_user_id) if row.actor_user_id else None
            items.append(
                {
                    "id": str(row.pk),
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
                    "actor_display_name": profile.display_name if profile else "",
                    "actor_avatar_url": profile.avatar_url if profile else None,
                    "verb": row.verb,
                    "field": row.field,
                    "old_value": row.old_value,
                    "new_value": row.new_value,
                    "created_at": row.created_at.isoformat(),
                }
            )
        return items, meta
