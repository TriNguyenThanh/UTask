import re

from django.conf import settings
from rest_framework.exceptions import ParseError
from rest_framework.response import Response

from apps.github_accounts.consent import CONSENT_TTL
from apps.github_accounts.consent_api import GitHubConsentView
from apps.github_accounts.validation import GITHUB_ID_PATTERN

from .services import (
    NONCE_COOKIE,
    complete_installation,
    list_installations,
    list_repositories,
    start_installation,
)


def response_data(data):
    return Response({"success": True, "data": data}, headers={"Cache-Control": "private, no-store"})


def pagination(request):
    if set(request.query_params) - {"page", "per_page"} or request.body:
        raise ParseError("Chỉ nhận page và per_page.")
    result = []
    for name, default, maximum in (("page", "1", 10000), ("per_page", "30", 100)):
        values = request.query_params.getlist(name)
        value = values[0] if values else default
        if len(values) > 1 or not re.fullmatch(r"[1-9][0-9]{0,4}", value) or int(value) > maximum:
            raise ParseError("Phân trang không hợp lệ.")
        result.append(int(value))
    return result


class GitHubInstallationStartView(GitHubConsentView):
    def post(self, request):
        if request.query_params or request.body:
            raise ParseError("Endpoint này không nhận query hoặc request body.")
        data, nonce = start_installation(user_id=request.user.id, bearer=self.bearer(request))
        response = response_data(data)
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


class GitHubInstallationCompleteView(GitHubConsentView):
    def post(self, request):
        body = request.data
        if (
            request.query_params
            or not isinstance(body, dict)
            or set(body) != {"state", "installation_id", "setup_action"}
            or not isinstance(body["state"], str)
            or not 20 <= len(body["state"]) <= 256
            or not isinstance(body["installation_id"], str)
            or not re.fullmatch(GITHUB_ID_PATTERN, body["installation_id"])
            or not isinstance(body["setup_action"], str)
            or body["setup_action"] not in {"install", "update", "request"}
        ):
            raise ParseError("Callback installation không hợp lệ.")
        data = complete_installation(
            user_id=request.user.id,
            bearer=self.bearer(request),
            nonce=request.COOKIES.get(NONCE_COOKIE),
            **body,
        )
        response = response_data(data)
        response.delete_cookie(NONCE_COOKIE, path="/", samesite="Lax")
        return response


class GitHubInstallationsView(GitHubConsentView):
    http_method_names = ["get", "options"]

    def get(self, request):
        page, per_page = pagination(request)
        return response_data(
            list_installations(user_id=request.user.id, page=page, per_page=per_page)
        )


class GitHubRepositoriesView(GitHubConsentView):
    http_method_names = ["get", "options"]

    def get(self, request, installation_id):
        if not re.fullmatch(GITHUB_ID_PATTERN, installation_id):
            raise ParseError("Installation ID không hợp lệ.")
        page, per_page = pagination(request)
        return response_data(
            list_repositories(
                user_id=request.user.id,
                installation_id=installation_id,
                page=page,
                per_page=per_page,
            )
        )
