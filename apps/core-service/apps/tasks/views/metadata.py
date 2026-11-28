from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import GenericAPIView

from apps.projects.queries import visible_project
from apps.projects.views import ERRORS
from apps.tasks.api_documentation import TASK
from apps.tasks.queries import project_metadata, visible_task
from apps.tasks.serializers import EpicSerializer, LabelSerializer
from apps.tasks.serializers.metadata import (
    DeletedEpicSerializer,
    DeletedLabelSerializer,
    EpicInputSerializer,
    LabelInputSerializer,
    TaskLabelsSerializer,
)
from apps.tasks.services.metadata import metadata_command, task_labels_command
from common.pagination import paginate
from common.responses import success_response
from config.api_documentation import envelope_schema

LABEL_RESPONSE = envelope_schema("LabelEnvelope", LabelSerializer)
EPIC_RESPONSE = envelope_schema("EpicEnvelope", EpicSerializer)


class MetadataListView(GenericAPIView):
    serializer_class = LabelInputSerializer
    kind = "label"

    def get(self, request, project_id):
        project = visible_project(request.user, project_id)
        serializer_class = LabelSerializer if self.kind == "label" else EpicSerializer
        rows, meta = paginate(
            project_metadata(project, self.kind),
            request.query_params,
            scope={"project": str(project_id), "kind": self.kind, "actor": str(request.user.id)},
        )
        return success_response(
            serializer_class(rows, many=True).data,
            meta=meta,
            message="Đã tải danh sách nhãn công việc."
            if self.kind == "label"
            else "Đã tải danh sách mục tiêu lớn.",
        )

    def post(self, request, project_id):
        visible_project(request.user, project_id, for_write=True)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return metadata_command(request.user, project_id, self.kind, serializer.validated_data)


class MetadataDetailView(MetadataListView):
    http_method_names = ["patch", "delete", "options"]

    def patch(self, request, project_id, subject_id):
        visible_project(request.user, project_id, for_write=True)
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return metadata_command(
            request.user, project_id, self.kind, serializer.validated_data, subject_id=subject_id
        )

    def delete(self, request, project_id, subject_id):
        visible_project(request.user, project_id, for_write=True)
        return metadata_command(
            request.user, project_id, self.kind, {}, subject_id=subject_id, delete=True
        )


class LabelListView(MetadataListView):
    @extend_schema(
        parameters=[OpenApiParameter("cursor", str), OpenApiParameter("page_size", int)],
        responses={
            200: envelope_schema("LabelsEnvelope", LabelSerializer, many=True, paginated=True),
            **ERRORS,
        },
    )
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)

    @extend_schema(
        request=LabelInputSerializer,
        responses={201: LABEL_RESPONSE, **ERRORS},
    )
    def post(self, *args, **kwargs):
        return super().post(*args, **kwargs)


class EpicListView(MetadataListView):
    kind = "epic"
    serializer_class = EpicInputSerializer

    @extend_schema(
        parameters=[OpenApiParameter("cursor", str), OpenApiParameter("page_size", int)],
        responses={
            200: envelope_schema("EpicsEnvelope", EpicSerializer, many=True, paginated=True),
            **ERRORS,
        },
    )
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)

    @extend_schema(
        request=EpicInputSerializer,
        responses={201: EPIC_RESPONSE, **ERRORS},
    )
    def post(self, *args, **kwargs):
        return super().post(*args, **kwargs)


class LabelDetailView(MetadataDetailView):
    @extend_schema(
        request=LabelInputSerializer,
        responses={200: LABEL_RESPONSE, **ERRORS},
    )
    def patch(self, *args, **kwargs):
        return super().patch(*args, **kwargs)

    @extend_schema(
        request=None,
        responses={200: envelope_schema("DeletedLabelEnvelope", DeletedLabelSerializer), **ERRORS},
    )
    def delete(self, *args, **kwargs):
        return super().delete(*args, **kwargs)


class EpicDetailView(MetadataDetailView):
    kind = "epic"
    serializer_class = EpicInputSerializer

    @extend_schema(
        request=EpicInputSerializer,
        responses={200: EPIC_RESPONSE, **ERRORS},
    )
    def patch(self, *args, **kwargs):
        return super().patch(*args, **kwargs)

    @extend_schema(
        request=None,
        responses={200: envelope_schema("DeletedEpicEnvelope", DeletedEpicSerializer), **ERRORS},
    )
    def delete(self, *args, **kwargs):
        return super().delete(*args, **kwargs)


class TaskLabelsView(GenericAPIView):
    serializer_class = TaskLabelsSerializer

    @extend_schema(request=TaskLabelsSerializer, responses={200: TASK, **ERRORS})
    def post(self, request, task_id):
        visible_task(request.user, task_id, for_write=True)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return task_labels_command(request.user, task_id, serializer.validated_data)
