"""Bounded internal HTTP adapter; Work remains the Project authority."""

import json
import re
from urllib.parse import quote, urlsplit
from uuid import UUID

import requests
from django.conf import settings
from django.db import connection
from rest_framework.exceptions import APIException

MAX_WORK_RESPONSE_BYTES = 65_536


class WorkUnavailable(APIException):
    status_code = 503
    default_detail = "Chưa thể xác minh dữ liệu từ Work Service."
    default_code = "WORK_UNAVAILABLE"


class WorkAccessDenied(APIException):
    status_code = 403
    default_detail = "Không có quyền đọc dữ liệu GitHub của Project."
    default_code = "WORK_ACCESS_DENIED"


def _project_id(value):
    try:
        result = UUID(str(value))
        if not result.int:
            raise ValueError()
        return str(result)
    except (ValueError, TypeError, AttributeError):
        raise WorkUnavailable() from None


class WorkClient:
    def _request(self, method, path, *, bearer=None, payload=None):
        try:
            base = getattr(settings, "INTEGRATION_WORK_URL", "")
            parsed = urlsplit(base)
            key = getattr(settings, "INTEGRATION_WORK_SERVICE_KEY", "")
            if (
                not isinstance(base, str)
                or parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
                or parsed.path not in {"", "/"}
                or any(character.isspace() for character in base)
                or not isinstance(key, str)
                or not key.isascii()
                or not key.isprintable()
                or key.strip() != key
                or not 32 <= len(key) <= 4096
                or connection.in_atomic_block
            ):
                raise WorkUnavailable()
            # Accessing port validates malformed/out-of-range configured ports.
            _ = parsed.port
            headers = {"X-Service-Key": key, "Accept": "application/json"}
            if bearer is not None:
                if (
                    not isinstance(bearer, str)
                    or not 1 <= len(bearer) <= 8192
                    or not bearer.isascii()
                    or any(character.isspace() or ord(character) < 33 for character in bearer)
                ):
                    raise WorkUnavailable()
                headers["Authorization"] = f"Bearer {bearer}"
            kwargs = {"json": payload} if payload is not None else {}
            with requests.request(
                method,
                base.rstrip("/") + path,
                headers=headers,
                timeout=(2, 3),
                allow_redirects=False,
                stream=True,
                **kwargs,
            ) as response:
                if response.status_code != 200:
                    raise WorkUnavailable()
                body = bytearray()
                for chunk in response.iter_content(chunk_size=4096):
                    if len(body) + len(chunk) > MAX_WORK_RESPONSE_BYTES:
                        raise WorkUnavailable()
                    body.extend(chunk)
                envelope = json.loads(body)
                if not isinstance(envelope, dict) or envelope.get("success") is not True:
                    raise WorkUnavailable()
                data = envelope["data"]
                if not isinstance(data, dict):
                    raise WorkUnavailable()
                return data
        except (
            requests.RequestException,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            RecursionError,
        ):
            raise WorkUnavailable() from None

    def receipt(self, project_id, operation_id):
        project = _project_id(project_id)
        if (
            not isinstance(operation_id, str)
            or not 1 <= len(operation_id) <= 100
            or operation_id in {".", ".."}
            or any(ord(character) < 32 for character in operation_id)
        ):
            raise WorkUnavailable()
        data = self._request(
            "GET",
            f"/api/v1/internal/integration/projects/{project}/github/operations/"
            + quote(operation_id, safe=""),
        )
        if (
            set(data)
            != {
                "applied",
                "project_id",
                "operation_id",
                "generation",
                "status",
                "repo_id",
                "source_version",
            }
            or data["applied"] is not True
            or data["project_id"] != project
            or data["operation_id"] != operation_id
            or type(data["generation"]) is not int
            or data["generation"] < 1
            or type(data["source_version"]) is not int
            or data["source_version"] < 1
            or data["status"] != "PENDING"
            or (
                data["repo_id"] is not None
                and (
                    not isinstance(data["repo_id"], str)
                    or re.fullmatch(r"[1-9][0-9]{0,99}", data["repo_id"]) is None
                )
            )
        ):
            raise WorkUnavailable()
        return data

    def authorize(self, project_id, bearer):
        project = _project_id(project_id)
        if bearer is None:
            raise WorkUnavailable()
        data = self._request(
            "POST",
            f"/api/v1/internal/integration/projects/{project}/authorize",
            bearer=bearer,
            payload={"action": "github.read"},
        )
        if (
            set(data) != {"project_id", "action", "allowed"}
            or data["project_id"] != project
            or data["action"] != "github.read"
            or type(data["allowed"]) is not bool
        ):
            raise WorkUnavailable()
        if not data["allowed"]:
            raise WorkAccessDenied()
        return True
