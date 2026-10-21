import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from rest_framework.exceptions import APIException


class DependencyUnavailable(APIException):
    status_code = 503
    default_detail = "Dịch vụ phụ thuộc hiện không khả dụng."


def request_json(method, url, **kwargs):
    try:
        response = requests.request(method, url, timeout=(2, 5), allow_redirects=False, **kwargs)
        if response.status_code != 200:
            raise ValueError()
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError()
        return body
    except (requests.RequestException, ValueError, TypeError) as exc:
        raise DependencyUnavailable() from exc


class IdentityClient:
    def jwks(self):
        body = request_json("GET", settings.IDENTITY_BASE_URL + "/.well-known/jwks.json")
        if not isinstance(body.get("keys"), list) or any(
            not isinstance(k, dict) for k in body["keys"]
        ):
            raise DependencyUnavailable()
        return body

    def session_active(self, token):
        if not settings.IDENTITY_NOTIFICATION_SERVICE_KEY:
            raise DependencyUnavailable()
        body = request_json(
            "POST",
            settings.IDENTITY_BASE_URL + "/api/v1/internal/auth/session-status",
            headers={
                "Authorization": "Bearer " + token,
                "X-Service-Key": settings.IDENTITY_NOTIFICATION_SERVICE_KEY,
            },
        )
        data = body.get("data") if body.get("success") is True else None
        if not isinstance(data, dict) or type(data.get("active")) is not bool:
            raise DependencyUnavailable()
        return data["active"]


def contact(user_id):
    if not settings.NOTIFICATION_SERVICE_TOKEN:
        raise DependencyUnavailable()
    body = request_json(
        "POST",
        settings.IDENTITY_BASE_URL + "/api/v1/internal/users/notification-contacts",
        headers={"X-Service-Token": settings.NOTIFICATION_SERVICE_TOKEN},
        json={"user_ids": [str(user_id)]},
    )
    users = body.get("users")
    if not isinstance(users, list):
        raise DependencyUnavailable()
    matches = [u for u in users if isinstance(u, dict) and u.get("user_id") == str(user_id)]
    if not matches:
        return None
    if len(matches) != 1:
        raise DependencyUnavailable()
    user = matches[0]
    try:
        validate_email(user.get("email", ""))
    except (ValidationError, TypeError):
        raise DependencyUnavailable() from None
    if not isinstance(user.get("email"), str) or user.get("account_status") not in {
        "ACTIVE",
        "PENDING_ACTIVATION",
    }:
        return None
    return user


def resolve(inbox, user_id):
    if not settings.NOTIFICATION_SERVICE_TOKEN:
        raise DependencyUnavailable()
    body = request_json(
        "POST",
        settings.WORK_BASE_URL + "/api/v1/internal/notifications/resolve",
        headers={"X-Service-Token": settings.NOTIFICATION_SERVICE_TOKEN},
        json={
            "user_id": str(user_id),
            "event_type": inbox.envelope["event_type"],
            "project_id": inbox.envelope["project_id"],
            "data": inbox.envelope["data"],
        },
    )
    if type(body.get("eligible")) is not bool:
        raise DependencyUnavailable()
    if not body["eligible"]:
        return None
    if not all(isinstance(body.get(k), str) for k in ["title", "body"]) or not valid_target(
        body.get("target")
    ):
        raise DependencyUnavailable()
    return body


def valid_target(target):
    if target is None:
        return True
    if not isinstance(target, dict) or not isinstance(target.get("kind"), str):
        return False
    fields = {
        "team-hub": {"courseId"},
        "team-formation": {"courseId"},
        "join-request": {"courseId"},
        "board-issue": {"projectId", "issueKey"},
        "code": {"projectId"},
        "course-deadline": {"courseId"},
        "backlog": {"projectId"},
    }.get(target.get("kind"))
    return (
        fields is not None
        and set(target) == fields | {"kind"}
        and all(isinstance(target[k], str) and bool(target[k]) for k in fields)
    )


def resolve_many(rows, user_id):
    """Resolve current access in bounded Work batches, preserving result order."""
    if not settings.NOTIFICATION_SERVICE_TOKEN:
        raise DependencyUnavailable()
    results = []
    for start in range(0, len(rows), 100):
        batch = rows[start : start + 100]
        body = request_json(
            "POST",
            settings.WORK_BASE_URL + "/api/v1/internal/notifications/resolve",
            headers={"X-Service-Token": settings.NOTIFICATION_SERVICE_TOKEN},
            json={
                "items": [
                    {
                        "user_id": str(user_id),
                        "event_type": row.inbox.envelope["event_type"],
                        "project_id": row.inbox.envelope["project_id"],
                        "data": row.inbox.envelope["data"],
                    }
                    for row in batch
                ]
            },
        )
        values = body.get("results")
        if not isinstance(values, list) or len(values) != len(batch):
            raise DependencyUnavailable()
        for value in values:
            if not isinstance(value, dict) or type(value.get("eligible")) is not bool:
                raise DependencyUnavailable()
            if value["eligible"] and (
                not all(isinstance(value.get(k), str) for k in ["title", "body"])
                or not valid_target(value.get("target"))
            ):
                raise DependencyUnavailable()
            results.append(value if value["eligible"] else None)
    return results
