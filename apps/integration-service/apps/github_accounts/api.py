from rest_framework.exceptions import ParseError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.api_errors import integration_exception_handler
from common.authentication import IdentityBearerAuthentication

from .credentials import authorization_status
from .models import GitHubAccount
from .services import unlink_github_account


def account_data(user_id, account):
    linked = account is not None and account.status == GitHubAccount.Status.LINKED
    return {
        "user_id": str(user_id),
        "status": account.status if account is not None else "UNLINKED",
        "authorization_status": authorization_status(user_id=user_id, account=account),
        "github_user_id": account.github_user_id if linked else None,
        "github_username": account.github_username if linked else None,
        "verified_at": account.verified_at.isoformat() if linked else None,
        "linked_at": account.linked_at.isoformat() if linked else None,
        "revoked_at": account.revoked_at.isoformat() if account and account.revoked_at else None,
        "source_version": account.source_version if account is not None else 0,
    }


class GitHubAccountView(APIView):
    authentication_classes = [IdentityBearerAuthentication]
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "delete", "head", "options"]

    def get_exception_handler(self):
        return integration_exception_handler

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        if request.method == "HEAD":
            response.data = None
        return response

    def require_empty_input(self, request):
        if request.query_params or request.body:
            raise ParseError("Endpoint này không nhận user_id, query hoặc request body.")

    def get(self, request):
        self.require_empty_input(request)
        account = GitHubAccount.objects.filter(user_id=request.user.id).first()
        return Response(
            {"success": True, "data": account_data(request.user.id, account)},
            headers={"Cache-Control": "private, no-store"},
        )

    def delete(self, request):
        self.require_empty_input(request)
        account = unlink_github_account(user_id=request.user.id)
        return Response(
            {"success": True, "data": account_data(request.user.id, account)},
            headers={"Cache-Control": "private, no-store"},
        )
