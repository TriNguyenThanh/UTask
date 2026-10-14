from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import GenericAPIView

from apps.collaboration.permissions import subject_access, verified_teacher_mentions
from apps.collaboration.queries import subject_comments, visible_comment
from apps.collaboration.serializers import (
    CommentInputSerializer,
    CommentSerializer,
    EditCommentSerializer,
)
from apps.collaboration.services import comment_command
from apps.projects.views import ERRORS
from common.pagination import paginate
from common.responses import success_response
from config.api_documentation import envelope_schema

COMMENT = envelope_schema("CommentEnvelope", CommentSerializer)
COMMENTS = envelope_schema("CommentsEnvelope", CommentSerializer, many=True, paginated=True)


class CommentCreateView(GenericAPIView):
    serializer_class = CommentInputSerializer

    @extend_schema(request=CommentInputSerializer, responses={201: COMMENT, **ERRORS})
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        task_id = payload.get("task_id")
        _, project, teacher = subject_access(
            request.user, task_id=task_id, project_id=payload.get("project_id"), for_feedback=True
        )
        recipients = verified_teacher_mentions(request.user, project, payload)
        return comment_command(
            request.user,
            project.pk,
            payload,
            task_id=task_id,
            teacher=teacher,
            teacher_mentions=recipients,
        )


class CommentDetailView(GenericAPIView):
    serializer_class = EditCommentSerializer

    @extend_schema(request=EditCommentSerializer, responses={200: COMMENT, **ERRORS})
    def patch(self, request, comment_id):
        comment = visible_comment(request.user, comment_id)
        _, project, teacher = subject_access(
            request.user, task_id=comment.task_id, project_id=comment.project_id, for_feedback=True
        )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        recipients = verified_teacher_mentions(request.user, project, serializer.validated_data)
        return comment_command(
            request.user,
            project.pk,
            serializer.validated_data,
            task_id=comment.task_id,
            comment_id=comment.pk,
            teacher=teacher,
            teacher_mentions=recipients,
        )

    @extend_schema(request=None, responses={200: COMMENT, **ERRORS})
    def delete(self, request, comment_id):
        comment = visible_comment(request.user, comment_id)
        _, project, teacher = subject_access(
            request.user, task_id=comment.task_id, project_id=comment.project_id, for_feedback=True
        )
        return comment_command(
            request.user,
            project.pk,
            {},
            task_id=comment.task_id,
            comment_id=comment.pk,
            teacher=teacher,
            delete=True,
        )


class CommentListView(GenericAPIView):
    serializer_class = CommentSerializer

    @extend_schema(
        parameters=[OpenApiParameter("cursor", str), OpenApiParameter("page_size", int)],
        responses={200: COMMENTS, **ERRORS},
    )
    def get(self, request, task_id=None, project_id=None):
        subject_access(request.user, task_id=task_id, project_id=project_id)
        rows = subject_comments(task_id=task_id, project_id=project_id)
        rows, meta = paginate(
            rows,
            request.query_params,
            scope={"actor": str(request.user.id), "task": str(task_id), "project": str(project_id)},
        )
        return success_response(
            CommentSerializer(rows, many=True).data,
            meta=meta,
            message="Đã tải danh sách bình luận.",
        )
