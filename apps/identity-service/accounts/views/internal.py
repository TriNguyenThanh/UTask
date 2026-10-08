from allauth.socialaccount.models import SocialAccount
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import ClassroomActorPermission, ServiceKeyPermission
from accounts.serializers.provisioning import ProvisionStudentsSerializer
from accounts.services.provisioning import provision_students, resend_import_activation


class ProvisionStudentsView(GenericAPIView):
    serializer_class = ProvisionStudentsSerializer
    permission_classes = [IsAuthenticated, ServiceKeyPermission, ClassroomActorPermission]
    service_callers = ("classroom",)

    @extend_schema(
        parameters=[
            OpenApiParameter("X-Service-Key", str, OpenApiParameter.HEADER, required=True),
            OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True),
        ],
        responses={
            200: inline_serializer(
                "ExistingProvisionData",
                fields={
                    "summary": serializers.DictField(child=serializers.IntegerField()),
                    "results": serializers.ListField(child=serializers.DictField()),
                },
            ),
            201: inline_serializer(
                "CreatedProvisionData",
                fields={
                    "summary": serializers.DictField(child=serializers.IntegerField()),
                    "results": serializers.ListField(child=serializers.DictField()),
                },
            ),
        },
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        status, body = provision_students(
            request, serializer.validated_data["students"], request.headers.get("Idempotency-Key")
        )
        return Response(body, status=status)


class InternalActivationResendView(APIView):
    permission_classes = [IsAuthenticated, ServiceKeyPermission, ClassroomActorPermission]
    service_callers = ("classroom",)
    success_message = "Hướng dẫn kích hoạt đã được đưa vào hàng đợi."

    @extend_schema(
        request=None,
        parameters=[OpenApiParameter("X-Service-Key", str, OpenApiParameter.HEADER, required=True)],
        responses={200: None},
    )
    def post(self, request, user_id):
        if request.data:
            raise serializers.ValidationError("Expected an empty body.")
        resend_import_activation(request, user_id)
        return Response(None)


class GitHubMappingView(APIView):
    authentication_classes = []
    permission_classes = [ServiceKeyPermission]
    service_callers = ("integration",)

    @extend_schema(
        parameters=[OpenApiParameter("X-Service-Key", str, OpenApiParameter.HEADER, required=True)],
        responses=inline_serializer(
            "GitHubMappingData",
            fields={
                "user_id": serializers.UUIDField(),
                "mapping": serializers.DictField(allow_null=True),
            },
        ),
    )
    def get(self, request, user_id):
        field = serializers.UUIDField()
        user_id = field.run_validation(user_id)
        account = (
            SocialAccount.objects.filter(
                provider="github", user_id=user_id, user__deleted_at__isnull=True
            )
            .select_related("user__profile")
            .first()
        )
        mapping = (
            {
                "provider_user_id": account.uid,
                "github_username": account.user.profile.github_username,
            }
            if account
            else None
        )
        return Response({"user_id": str(user_id), "mapping": mapping})
