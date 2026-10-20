from rest_framework.authentication import get_authorization_header
from rest_framework.exceptions import ParseError, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.api_errors import integration_exception_handler
from common.authentication import IdentityBearerAuthentication
from common.internal_auth import InternalServicePermission

from . import services, validation


def response_data(data):
    return Response({"success": True, "data": data}, headers={"Cache-Control": "no-store"})


class InternalConnectionView(APIView):
    allowed_callers = ("work",)
    authentication_classes = []
    permission_classes = [InternalServicePermission]
    http_method_names = ["post"]

    def get_exception_handler(self):
        return integration_exception_handler

    def perform_authentication(self, request):
        # Internal trust boundary is checked before forwarding a Bearer to Identity.
        if not InternalServicePermission().has_permission(request, self):
            raise PermissionDenied("Caller dịch vụ không được phép.")
        services.require_connections()
        return super().perform_authentication(request)

    def body(self, request, validator):
        if request.query_params or request.content_type != "application/json":
            raise ParseError("Chỉ nhận JSON body, không nhận query.")
        return validator(request.data)


class ActorConnectionView(InternalConnectionView):
    authentication_classes = [IdentityBearerAuthentication]
    permission_classes = [InternalServicePermission, IsAuthenticated]


class PrepareConnectionView(ActorConnectionView):
    def post(self, request, project_id):
        return response_data(
            services.prepare_connection(
                project_id=validation.project_uuid(project_id),
                user_id=request.user.id,
                body=self.body(request, validation.prepare_payload),
            )
        )


class ConfirmConnectionView(InternalConnectionView):
    def post(self, request, project_id):
        return response_data(
            services.confirm_connection(
                project_id=validation.project_uuid(project_id),
                **self.body(request, validation.command_payload),
            )
        )


class AbortConnectionView(InternalConnectionView):
    def post(self, request, project_id):
        return response_data(
            services.abort_connection(
                project_id=validation.project_uuid(project_id),
                **self.body(request, validation.command_payload),
            )
        )


class ConnectionOperationView(InternalConnectionView):
    http_method_names = ["get"]

    def get(self, request, project_id, operation_id):
        if request.query_params or request.body:
            raise ParseError("Endpoint không nhận query hoặc body.")
        return response_data(
            services.connection_operation(
                project_id=validation.project_uuid(project_id),
                operation_id=validation.operation_id(operation_id),
            )
        )


class VerifyReferenceView(ActorConnectionView):
    def post(self, request, project_id):
        return response_data(
            services.verify_reference(
                project_id=validation.project_uuid(project_id),
                body=self.body(request, validation.reference_payload),
            )
        )


class GitHubContextView(ActorConnectionView):
    allowed_callers = ("ai",)
    http_method_names = ["get"]

    def get(self, request, project_id):
        if request.query_params or request.body:
            raise ParseError("Endpoint không nhận query hoặc body.")
        data = services.context_document(
            project_id=validation.project_uuid(project_id),
            bearer=get_authorization_header(request).split()[1].decode("ascii"),
        )
        return Response(data, headers={"Cache-Control": "no-store"})
