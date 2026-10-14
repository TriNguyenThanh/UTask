from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import GenericAPIView

from apps.messaging.services.receipts import receipt_scope, require_key
from apps.projects import queries
from apps.projects.queries.projects import project_list
from apps.projects.serializers.projects import (
    CreateProjectSerializer,
    PatchProjectSerializer,
    ProjectListMetaSerializer,
    ProjectSerializer,
    VersionSerializer,
)
from apps.projects.services.projects import (
    archive_project,
    create_project,
    update_project,
)
from common.responses import success_response
from config.api_documentation import ERRORS, LIST_PARAMETERS, envelope_schema
from infrastructure.classroom import classroom_client

PROJECT = envelope_schema("ProjectEnvelope", ProjectSerializer)


PROJECT_LIST = envelope_schema("ProjectListEnvelope", ProjectSerializer, many=True, paginated=True)
PROJECT_LIST.fields["meta"] = ProjectListMetaSerializer(allow_null=True)


class ProjectListCreateView(GenericAPIView):
    serializer_class = CreateProjectSerializer

    @extend_schema(
        operation_id="projects_list",
        parameters=LIST_PARAMETERS + [OpenApiParameter("classroom_group_id", str)],
        responses={200: PROJECT_LIST, **ERRORS},
    )
    def get(self, request):
        rows, meta = project_list(request.user, request.query_params)
        return success_response(
            ProjectSerializer(rows, many=True).data, meta=meta, message="Đã lấy danh sách dự án."
        )

    @extend_schema(
        request=CreateProjectSerializer,
        parameters=[
            OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)
        ],
        responses={201: PROJECT, **ERRORS},
    )
    def post(self, request):
        key = require_key(request)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        snapshot = classroom_client().group_snapshot(payload["classroom_group_id"], request.user)
        return create_project(request.user, payload, snapshot, receipt_scope(request, key))


class ProjectDetailView(GenericAPIView):
    serializer_class = PatchProjectSerializer

    @extend_schema(responses={200: PROJECT, **ERRORS})
    def get(self, request, project_id):
        return success_response(
            ProjectSerializer(queries.visible_project(request.user, project_id)).data,
            message="Đã lấy thông tin dự án.",
        )

    @extend_schema(request=PatchProjectSerializer, responses={200: PROJECT, **ERRORS})
    def patch(self, request, project_id):
        queries.visible_project(request.user, project_id, for_write=True)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return update_project(request.user, project_id, serializer.validated_data)


class ProjectArchiveView(GenericAPIView):
    serializer_class = VersionSerializer
    archive = True

    @extend_schema(request=VersionSerializer, responses={200: PROJECT, **ERRORS})
    def post(self, request, project_id):
        queries.visible_project(request.user, project_id, for_write=True)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return archive_project(
            request.user,
            project_id,
            serializer.validated_data["expected_version"],
            archive=self.archive,
        )
