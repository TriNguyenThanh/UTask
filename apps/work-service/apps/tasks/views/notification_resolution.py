from datetime import timedelta
from uuid import UUID

from django.db import connection
from django.utils import timezone
from rest_framework import serializers
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.collaboration.models import Comment
from apps.projects.models import Project
from apps.tasks.models import Task
from common.notification_permission import NotificationServicePermission
from common.serializers import StrictInputSerializer

EVENT_TITLES = {
    "task.assigned": "Bạn được giao công việc",
    "task.transitioned": "Công việc đã chuyển trạng thái",
    "task.deadline.reminder": "Nhắc hạn công việc",
    "comment.mentions.added": "Bạn được nhắc tên trong bình luận",
    "teacher.feedback.added": "Giảng viên đã gửi nhận xét",
}
DENIED = {"eligible": False, "title": "", "body": "", "target": None}


class NotificationResolutionSerializer(StrictInputSerializer):
    user_id = serializers.UUIDField()
    event_type = serializers.ChoiceField(choices=list(EVENT_TITLES))
    project_id = serializers.UUIDField()
    data = serializers.DictField()


class NotificationResolutionBatchSerializer(StrictInputSerializer):
    items = NotificationResolutionSerializer(many=True, allow_empty=False, max_length=100)


def valid_id(value):
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def current_deadline_revision(task):
    with connection.cursor() as cursor:
        cursor.execute(
            """WITH history AS (
              SELECT project_sequence, data->'data'->>'due_date' AS due,
                LAG(data->'data'->>'due_date') OVER (ORDER BY project_sequence) AS previous_due
              FROM outbox_events WHERE project_id=%s AND aggregate_type='task'
                AND aggregate_id=%s AND (data->'data') ? 'due_date'
                AND event_type <> 'task.deadline.reminder'
            ) SELECT MAX(project_sequence) FROM history WHERE due IS DISTINCT FROM previous_due""",
            [task.project_id, str(task.pk)],
        )
        return str(cursor.fetchone()[0] or "created")


def resolve_notification(user_id, event_type, project_id, data, *, project_cache=None):
    project_cache = project_cache if project_cache is not None else {}
    key = (user_id, project_id)
    if key not in project_cache:
        project_cache[key] = Project.objects.filter(
            pk=project_id,
            deleted_at__isnull=True,
            archived_at__isnull=True,
            members__user_id=user_id,
            members__status="ACTIVE",
        ).first()
    project = project_cache[key]
    if project is None or str(data.get("actor_user_id", "")) == str(user_id):
        return DENIED.copy()
    task = None
    if event_type in {"comment.mentions.added", "teacher.feedback.added"}:
        comment_id = valid_id(data.get("comment_id") or data.get("id"))
        if comment_id is None:
            return DENIED.copy()
        comment = (
            Comment.objects.select_related("task__state")
            .filter(
                pk=comment_id,
                deleted_at__isnull=True,
            )
            .first()
        )
        if comment is None:
            return DENIED.copy()
        task = comment.task
        if (task.project_id if task else comment.project_id) != project.pk:
            return DENIED.copy()
        if comment.user_id == user_id:
            return DENIED.copy()
        if (
            event_type == "comment.mentions.added"
            and not comment.mentions.filter(user_id=user_id).exists()
        ):
            return DENIED.copy()
        if event_type == "teacher.feedback.added" and not comment.is_teacher_feedback:
            return DENIED.copy()
    else:
        task_id = valid_id(data.get("task_id") or data.get("id"))
        if task_id is None:
            return DENIED.copy()
        task = Task.objects.select_related("state").filter(pk=task_id, project=project).first()
        if task is None or not task.assignments.filter(user_id=user_id).exists():
            return DENIED.copy()
    if task and (task.deleted_at or task.archived_at):
        return DENIED.copy()
    if event_type == "task.deadline.reminder":
        day = timezone.localdate(timezone=timezone.get_fixed_timezone(420))
        if (
            task.state.group in {"COMPLETED", "CANCELLED"}
            or task.due_date is None
            or task.due_date > day + timedelta(days=1)
            or data.get("due_date") != task.due_date.isoformat()
            or data.get("deadline_revision") != current_deadline_revision(task)
        ):
            return DENIED.copy()
    if event_type == "task.transitioned" and str(data.get("state_id")) != str(task.state_id):
        return DENIED.copy()
    target = (
        {
            "kind": "board-issue",
            "projectId": str(project.pk),
            "issueKey": f"{project.identifier}-{task.sequence_id}",
        }
        if task
        else {"kind": "backlog", "projectId": str(project.pk)}
    )
    body = f"{project.identifier}-{task.sequence_id}: {task.title}" if task else project.name
    return {"eligible": True, "title": EVENT_TITLES[event_type], "body": body, "target": target}


class NotificationResolutionView(APIView):
    authentication_classes = []
    permission_classes = [NotificationServicePermission]
    renderer_classes = [JSONRenderer]

    def post(self, request):
        if isinstance(request.data, dict) and "items" in request.data:
            serializer = NotificationResolutionBatchSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            project_cache = {}
            return Response(
                {
                    "results": [
                        resolve_notification(**item, project_cache=project_cache)
                        for item in serializer.validated_data["items"]
                    ]
                }
            )
        serializer = NotificationResolutionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(resolve_notification(**serializer.validated_data))
