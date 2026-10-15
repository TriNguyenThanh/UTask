from drf_spectacular.utils import extend_schema
from rest_framework.generics import GenericAPIView

from apps.projects import queries
from apps.projects.serializers.members import CapacitySerializer, MemberSerializer
from apps.projects.services.projects import (
    set_capacity,
)
from common.pagination import paginate
from common.responses import success_response
from config.api_documentation import ERRORS, LIST_PARAMETERS, envelope_schema

MEMBER = envelope_schema("MemberEnvelope", MemberSerializer)


MEMBERS = envelope_schema("MemberListEnvelope", MemberSerializer, many=True, paginated=True)


class ProjectMemberListView(GenericAPIView):
    serializer_class = MemberSerializer

    @extend_schema(parameters=LIST_PARAMETERS, responses={200: MEMBERS, **ERRORS})
    def get(self, request, project_id):
        project = queries.visible_project(request.user, project_id)
        status = request.query_params.get("status", "ACTIVE")
        rows, meta = paginate(
            queries.member_queryset(project, status),
            request.query_params,
            scope={"project": str(project_id), "actor": str(request.user.id), "status": status},
            time_field="joined_at",
        )
        return success_response(
            MemberSerializer(rows, many=True).data,
            meta=meta,
            message="Đã lấy danh sách thành viên dự án.",
        )


class CapacityView(GenericAPIView):
    serializer_class = CapacitySerializer

    @extend_schema(request=CapacitySerializer, responses={200: MEMBER, **ERRORS})
    def patch(self, request, project_id, user_id):
        queries.visible_project(request.user, project_id, for_write=True)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return set_capacity(
            request.user, project_id, user_id, serializer.validated_data["weekly_capacity"]
        )
