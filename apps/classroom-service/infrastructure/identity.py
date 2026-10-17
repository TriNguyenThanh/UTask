import logging

import requests
from django.conf import settings

from common.errors import ClassroomError

logger = logging.getLogger(__name__)


class IdentityClient:
    def request_data(self, method, path, token, *, data=None, key=None):
        headers = {"Authorization": "Bearer " + token}
        if path.startswith("/api/v1/internal/"):
            headers["X-Service-Key"] = settings.IDENTITY_CLASSROOM_SERVICE_KEY
        if key:
            headers["Idempotency-Key"] = str(key)
        try:
            response = requests.request(
                method,
                settings.IDENTITY_BASE_URL + path,
                headers=headers,
                json=data,
                timeout=settings.BACKEND_HTTP_TIMEOUT,
                allow_redirects=False,
            )
            if not 200 <= response.status_code < 300:
                raise ValueError("Identity request refused")
            body = response.json()
            if (
                not isinstance(body, dict)
                or body.get("success") is not True
                or not isinstance(body.get("data"), dict)
            ):
                raise ValueError("Invalid Identity response")
            return body["data"]
        except (requests.RequestException, ValueError, TypeError) as exc:
            logger.error(
                "Identity dependency failed operation=%s error=%s", path, type(exc).__name__
            )
            raise ClassroomError(
                "IDENTITY_UNAVAILABLE", "Không thể xác minh thông tin tài khoản lúc này.", 503
            ) from exc

    def current_user(self, token):
        data = self.request_data("GET", "/users/me", token)
        if (
            not isinstance(data.get("id"), str)
            or not isinstance(data.get("roles"), list)
            or any(not isinstance(role, str) for role in data["roles"])
        ):
            raise ClassroomError(
                "IDENTITY_UNAVAILABLE", "Không thể xác minh thông tin tài khoản lúc này.", 503
            )
        return data

    def users(self, token, ids):
        data = self.request_data(
            "POST", "/users/batch", token, data={"user_ids": [str(x) for x in ids]}
        )
        if not isinstance(data.get("users"), list) or any(
            not isinstance(row, dict)
            or not isinstance(row.get("id"), str)
            or not isinstance(row.get("roles"), list)
            or any(not isinstance(role, str) for role in row["roles"])
            or not isinstance(row.get("account_status"), str)
            for row in data["users"]
        ):
            raise ClassroomError(
                "IDENTITY_UNAVAILABLE", "Không thể lấy thông tin tài khoản lúc này.", 503
            )
        return data["users"]

    def provision(self, token, rows, key):
        data = self.request_data(
            "POST",
            "/api/v1/internal/users/provision-students",
            token,
            data={"students": rows},
            key=key,
        )
        results = data.get("results")
        if (
            not isinstance(results, list)
            or len(results) != len(rows)
            or any(
                not isinstance(row, dict)
                or not isinstance(row.get("account_result"), str)
                or row["account_result"] not in {"CREATED", "EXISTING", "FAILED", "FLAGGED"}
                or (row.get("reason") is not None and not isinstance(row["reason"], str))
                or (row.get("user_id") is not None and not isinstance(row["user_id"], str))
                or (
                    row.get("account_status") is not None
                    and not isinstance(row["account_status"], str)
                )
                for row in results
            )
        ):
            raise ClassroomError(
                "IDENTITY_UNAVAILABLE", "Không thể xác minh kết quả xử lý danh sách tài khoản.", 503
            )
        return data

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
            raise ClassroomError(
                "IDENTITY_UNAVAILABLE", "Dịch vụ xác thực hiện không khả dụng.", 503
            ) from exc

    def session_active(self, token):
        if not settings.IDENTITY_CLASSROOM_SERVICE_KEY:
            logger.error(
                "Identity dependency not configured operation=session-status caller=classroom"
            )
            raise ClassroomError(
                "IDENTITY_UNAVAILABLE", "Dịch vụ xác thực hiện không khả dụng.", 503
            )
        try:
            response = requests.post(
                settings.IDENTITY_BASE_URL + "/api/v1/internal/auth/session-status",
                headers={
                    "Authorization": "Bearer " + token,
                    "X-Service-Key": settings.IDENTITY_CLASSROOM_SERVICE_KEY,
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
            raise ClassroomError(
                "IDENTITY_UNAVAILABLE",
                "Không thể xác minh phiên đăng nhập của người dùng.",
                503,
            ) from exc
