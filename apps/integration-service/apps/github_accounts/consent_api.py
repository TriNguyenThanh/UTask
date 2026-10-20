from django.conf import settings
from rest_framework.authentication import get_authorization_header
from rest_framework.exceptions import ParseError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.api_errors import integration_exception_handler
from common.authentication import IdentityBearerAuthentication

from .api import account_data
from .consent import CONSENT_TTL, NONCE_COOKIE, complete_consent, start_consent


class GitHubConsentView(APIView):
    authentication_classes = [IdentityBearerAuthentication]
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "options"]

    def get_exception_handler(self):
        return integration_exception_handler

    def bearer(self, request):
        return get_authorization_header(request).split()[1].decode("ascii")


class GitHubConsentStartView(GitHubConsentView):
    def post(self, request):
        if request.query_params or request.body:
            raise ParseError("Endpoint này không nhận query hoặc request body.")
        data, nonce = start_consent(user_id=request.user.id, bearer=self.bearer(request))
        response = Response(
            {"success": True, "data": data}, headers={"Cache-Control": "private, no-store"}
        )
        response.set_cookie(
            NONCE_COOKIE,
            nonce,
            max_age=CONSENT_TTL,
            httponly=True,
            samesite="Lax",
            secure=settings.INTEGRATION_CONSENT_COOKIE_SECURE,
            path="/",
        )
        return response


class GitHubConsentCompleteView(GitHubConsentView):
    def post(self, request):
        body = request.data
        if (
            request.query_params
            or not isinstance(body, dict)
            or set(body) != {"code", "state"}
            or not isinstance(body["code"], str)
            or not 1 <= len(body["code"]) <= 2048
            or not isinstance(body["state"], str)
            or not 20 <= len(body["state"]) <= 256
        ):
            raise ParseError("Chỉ nhận code và state hợp lệ từ consent.")
        account = complete_consent(
            user_id=request.user.id,
            bearer=self.bearer(request),
            state=body["state"],
            code=body["code"],
            nonce=request.COOKIES.get(NONCE_COOKIE),
        )
        response = Response(
            {"success": True, "data": account_data(request.user.id, account)},
            headers={"Cache-Control": "private, no-store"},
        )
        response.delete_cookie(
            NONCE_COOKIE,
            path="/",
            samesite="Lax",
        )
        return response
