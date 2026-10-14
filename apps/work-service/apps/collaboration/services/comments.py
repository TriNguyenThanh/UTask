from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from apps.collaboration.models import Comment, CommentMention
from apps.collaboration.queries import comment_queryset
from apps.collaboration.serializers import CommentSerializer
from apps.collaboration.serializers.events import (
    MentionIntentSerializer,
    TeacherFeedbackEventSerializer,
)
from apps.messaging.services import emit_event, record_activity
from apps.projects.permissions import active_member
from apps.projects.services.locking import lock_project
from apps.tasks.models import Task
from common.content import clean_content
from common.errors import WorkError
from common.responses import success_response
from infrastructure.collaboration_scope import VerifiedFeedbackScope


def comment_command(
    actor,
    project_id,
    payload,
    *,
    task_id=None,
    comment_id=None,
    teacher=False,
    teacher_mentions=frozenset(),
    delete=False,
):
    with transaction.atomic():
        project = lock_project(project_id)
        member = active_member(project, actor)
        if member is None:
            if not isinstance(teacher, VerifiedFeedbackScope):
                raise NotFound("Không tìm thấy đối tượng bình luận yêu cầu.")
            teacher.validate(actor, project)
        task = (
            Task.objects.select_for_update()
            .filter(pk=task_id, project=project, deleted_at__isnull=True)
            .first()
            if task_id
            else None
        )
        if (task_id and task is None) or project.archived_at or (task and task.archived_at):
            raise WorkError(
                "INVALID_OPERATION", "Nội dung được bình luận hiện không thể chỉnh sửa."
            )
        comment = (
            Comment.objects.select_for_update()
            .filter(pk=comment_id, deleted_at__isnull=True)
            .first()
            if comment_id
            else None
        )
        if comment_id and (
            comment is None
            or comment.task_id != task_id
            or comment.project_id != (None if task_id else project.pk)
        ):
            raise NotFound("Không tìm thấy bình luận yêu cầu.")
        if (
            comment
            and comment.user_id != actor.id
            and (not delete or member is None or member.role != "LEADER")
        ):
            raise WorkError(
                "PERMISSION_DENIED",
                "Chỉ tác giả mới có quyền sửa bình luận; tác giả hoặc trưởng nhóm có quyền xóa.",
                403,
            )
        if delete:
            comment.deleted_at = timezone.now()
            comment.save(update_fields=["deleted_at", "updated_at"])
            verb, status = "deleted", 200
        else:
            html, text, parsed = clean_content(payload["content_html"])
            mentions = parsed | set(payload.get("mentioned_user_ids", []))
            active = set(
                project.members.filter(status="ACTIVE", user_id__in=mentions).values_list(
                    "user_id", flat=True
                )
            )
            if mentions - active - set(teacher_mentions):
                raise WorkError(
                    "VALIDATION_ERROR",
                    "Người được nhắc tên (@mention) không thuộc phạm vi dự án hiện tại.",
                    422,
                )
            previous = set(comment.mentions.values_list("user_id", flat=True)) if comment else set()
            if comment:
                old = {"content_html": comment.content_html, "mentioned_user_ids": sorted(previous)}
                comment.content_html, comment.content_stripped = html, text
                comment.save(update_fields=["content_html", "content_stripped", "updated_at"])
                record_activity(
                    comment,
                    actor.id,
                    "updated",
                    field="content",
                    old=old,
                    new={"content_html": html, "mentioned_user_ids": sorted(mentions)},
                )
                verb, status = "updated", 200
            else:
                comment = Comment.objects.create(
                    task=task,
                    project=None if task else project,
                    user_id=actor.id,
                    content_html=html,
                    content_stripped=text,
                    is_teacher_feedback=teacher and member is None,
                )
                verb, status = "created", 201
            CommentMention.objects.filter(comment=comment, user_id__in=previous - mentions).delete()
            CommentMention.objects.bulk_create(
                [
                    CommentMention(comment=comment, user_id=user_id)
                    for user_id in sorted(mentions - previous)
                ]
            )
            if mentions - previous:
                emit_event(
                    project,
                    "comment.mentions.added",
                    MentionIntentSerializer(
                        {
                            "comment_id": str(comment.pk),
                            "task_id": str(task.pk) if task else None,
                            "recipient_ids": [str(value) for value in sorted(mentions - previous)],
                            "actor_user_id": str(actor.id),
                        }
                    ).data,
                    aggregate_type="comment",
                    aggregate_id=comment.pk,
                )
        data = CommentSerializer(comment_queryset().get(pk=comment.pk)).data
        if verb != "updated":
            record_activity(comment, actor.id, verb, new=data)
        project.board_revision += 1
        project.save(update_fields=["board_revision"])
        emit_event(
            project, "comment." + verb, data, aggregate_type="comment", aggregate_id=comment.pk
        )
        if verb == "created" and comment.is_teacher_feedback:
            emit_event(
                project,
                "teacher.feedback.added",
                TeacherFeedbackEventSerializer(
                    comment_queryset().get(pk=comment.pk),
                    context={
                        "scope_source_version": teacher.source_version,
                        "recipient_ids": list(
                            project.members.filter(status="ACTIVE").values_list(
                                "user_id", flat=True
                            )
                        ),
                    },
                ).data,
                aggregate_type="comment",
                aggregate_id=comment.pk,
            )
        return success_response(
            data,
            status=status,
            message={
                "created": "Đã gửi nhận xét của giảng viên."
                if comment.is_teacher_feedback
                else "Đã gửi bình luận.",
                "updated": "Đã cập nhật bình luận.",
                "deleted": "Đã xóa bình luận.",
            }[verb],
        )
