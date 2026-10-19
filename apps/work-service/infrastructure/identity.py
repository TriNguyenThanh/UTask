import logging
from uuid import UUID

import requests
from django.conf import settings

from common.errors import WorkError

logger = logging.getLogger(__name__)


class IdentityClient:
    def current_user(self, token):
        if not isinstance(token, str) or not token:
            raise WorkError("IDENTITY_UNAVAILABLE", "Chưa thể xác minh tài khoản của bạn.", 503)
        try:
            response = requests.get(
                settings.IDENTITY_BASE_URL + "/users/me",
                headers={"Authorization": "Bearer " + token},
                timeout=settings.BACKEND_HTTP_TIMEOUT,
                allow_redirects=False,
            )
            if response.status_code != 200:
                raise ValueError("Identity current-user request refused")
            body = response.json()
            data = (
                body.get("data") if isinstance(body, dict) and body.get("success") is True else None
            )
            if (
                not isinstance(data, dict)
                or not isinstance(data.get("id"), str)
                or not isinstance(data.get("roles"), list)
                or any(not isinstance(role, str) for role in data["roles"])
            ):
                raise ValueError("Invalid current-user response")
            UUID(data["id"])
            return data
        except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
            logger.warning(
                "Identity dependency failed operation=current-user error=%s", type(exc).__name__
            )
            raise WorkError(
                "IDENTITY_UNAVAILABLE", "Chưa thể xác minh tài khoản của bạn.", 503
            ) from exc

    def jwks(self):
        try:
            response = requests.get(
                settings.IDENTITY_BASE_URL + "/.well-known/jwks.json",
                timeout=settings.BACKEND_HTTP_TIMEOUT,
                allow_redirects=False,
            )
            response.raise_for_status()
            if 300 <= response.status_code < 400:
                raise ValueError("Identity redirect refused")
            data = response.json()
            if (
                not isinstance(data, dict)
                or not isinstance(data.get("keys"), list)
                or any(not isinstance(key, dict) for key in data["keys"])
            ):
                raise ValueError("Invalid JWKS")
            return data
        except (requests.RequestException, ValueError) as exc:
            logger.error(
                "Identity dependency failed operation=jwks upstream_status=%s error=%s",
                getattr(getattr(exc, "response", None), "status_code", "-"),
                type(exc).__name__,
            )
            raise WorkError(
                "IDENTITY_UNAVAILABLE", "Dịch vụ xác thực hiện không khả dụng.", 503
            ) from exc

    def session_active(self, token):
        if not settings.IDENTITY_WORK_SERVICE_KEY:
            logger.error("Identity dependency not configured operation=session-status caller=work")
            raise WorkError("IDENTITY_UNAVAILABLE", "Dịch vụ xác thực hiện không khả dụng.", 503)
        try:
            response = requests.post(
                settings.IDENTITY_BASE_URL + "/api/v1/internal/auth/session-status",
                headers={
                    "Authorization": "Bearer " + token,
                    "X-Service-Key": settings.IDENTITY_WORK_SERVICE_KEY,
                },
                timeout=settings.BACKEND_HTTP_TIMEOUT,
                allow_redirects=False,
            )
            response.raise_for_status()
            if 300 <= response.status_code < 400:
                raise ValueError("Identity redirect refused")
            body = response.json()
            data = body.get("data") if body.get("success") is True else None
            if not isinstance(data, dict) or type(data.get("active")) is not bool:
                raise ValueError("Invalid session-status envelope")
            return data["active"]
        except (requests.RequestException, ValueError, AttributeError) as exc:
            logger.error(
                "Identity dependency failed operation=session-status upstream_status=%s error=%s",
                getattr(getattr(exc, "response", None), "status_code", "-"),
                type(exc).__name__,
            )
            raise WorkError(
                "IDENTITY_UNAVAILABLE",
                "Không thể xác minh phiên đăng nhập của người dùng.",
                503,
            ) from exc
