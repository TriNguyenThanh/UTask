from uuid import uuid4

from drf_spectacular.utils import extend_schema
from rest_framework.generics import GenericAPIView

from apps.integrations.serializers.accounts import (
    MappingSerializer,
    RequestedSerializer,
    UsernameInputSerializer,
)
from apps.integrations.services.accounts import declare_username, request_verification
from apps.messaging.services.receipts import receipt_scope, require_key
from apps.projects.queries.projects import visible_project
from common.serializers import StrictInputSerializer
from config.api_documentation import ERRORS, envelope_schema


class UsernameView(GenericAPIView):
    serializer_class = UsernameInputSerializer

    @extend_schema(
        request=UsernameInputSerializer,
        responses={200: envelope_schema("GitHubMappingEnvelope", MappingSerializer), **ERRORS},
    )
    def patch(self, request, project_id, user_id):
        visible_project(request.user, project_id, for_write=True)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return declare_username(
            request.user, project_id, user_id, serializer.validated_data["github_username"]
        )


class VerificationRequestView(GenericAPIView):
    serializer_class = StrictInputSerializer

    @extend_schema(
        request=None,
        responses={
            200: envelope_schema("GitHubVerificationRequestedEnvelope", RequestedSerializer),
            **ERRORS,
        },
    )
    def post(self, request, project_id, user_id):
        visible_project(request.user, project_id, for_write=True)
        self.get_serializer(data=request.data).is_valid(raise_exception=True)
        key = require_key(request) if request.headers.get("Idempotency-Key") else str(uuid4())
        return request_verification(request.user, project_id, user_id, receipt_scope(request, key))
