from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from infrastructure.identity import IdentityUserClient


class IdentityBearerAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return "Bearer"

    def authenticate(self, request):
        try:
            value = get_authorization_header(request)
        except UnicodeEncodeError as exc:
            raise AuthenticationFailed("Authorization Bearer không hợp lệ.") from exc
        if not value:
            return None
        parts = value.split()
        if len(parts) != 2 or parts[0].lower() != b"bearer" or len(parts[1]) > 8192:
            raise AuthenticationFailed("Authorization Bearer không hợp lệ.")
        try:
            bearer = parts[1].decode("ascii")
        except UnicodeDecodeError as exc:
            raise AuthenticationFailed("Authorization Bearer không hợp lệ.") from exc
        return IdentityUserClient().current_user(bearer), None
