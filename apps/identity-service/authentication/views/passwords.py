"""Initial password setup for OAuth-only accounts lacking a usable password."""

from dj_rest_auth.jwt_auth import unset_jwt_cookies
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from authentication.serializers.passwords import IdentityPasswordSetSerializer
from authentication.services.password_service import PasswordService


@extend_schema_view(
    post=extend_schema(
        request=IdentityPasswordSetSerializer,
        responses={200: None},
    )
)
class PasswordSetView(GenericAPIView):
    serializer_class = IdentityPasswordSetSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        PasswordService.set_initial_password(request, serializer.validated_data["new_password1"])
        response = Response(
            {"detail": "Đặt mật khẩu thành công. Vui lòng đăng nhập lại bằng mật khẩu mới."}
        )
        unset_jwt_cookies(response)
        return response
