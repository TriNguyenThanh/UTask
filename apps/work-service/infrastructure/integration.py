import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote, urlparse
from uuid import UUID

import requests
from django.conf import settings
from django.db import connection
from django.utils.dateparse import parse_datetime
from django.utils.module_loading import import_string

from common.errors import WorkError

logger = logging.getLogger(__name__)


def source_error(message):
    logger.warning("GitHub verification rejected: %s", message)
    return WorkError(
        "INTEGRATION_UNAVAILABLE",
        "Chưa thể xác minh thông tin GitHub để thực hiện yêu cầu này.",
        503,
    )


def validate_version(value):
    if type(value) is not int or value < 0:
        raise source_error("Phiên bản dữ liệu từ dịch vụ tích hợp không hợp lệ.")


@dataclass(frozen=True)
class ConnectionFact:
    """Internal Work adapter result; external Integration schema remains owner-defined."""

    project_id: UUID
    operation_id: str
    generation: int
    source_version: int
    status: str
    repo_id: str | None
    repo_owner: str | None
    repo_name: str | None
    default_branch: str | None
    synced_at: datetime

    def validate(self):
        validate_version(self.generation)
        validate_version(self.source_version)
        if (
            not isinstance(self.project_id, UUID)
            or self.status not in {"PENDING", "CONNECTED", "DISCONNECTED"}
            or not isinstance(self.operation_id, str)
            or not self.operation_id
            or len(self.operation_id) > 100
            or not isinstance(self.synced_at, datetime)
            or self.synced_at.tzinfo is None
        ):
            raise source_error("Thông tin kết nối kho lưu trữ không hợp lệ.")
        for value, limit in (
            (self.repo_id, 100),
            (self.repo_owner, 100),
            (self.repo_name, 255),
            (self.default_branch, 100),
        ):
            if value is not None and (not isinstance(value, str) or len(value) > limit):
                raise source_error("Thông tin kho lưu trữ mã nguồn không hợp lệ.")
        if self.status == "CONNECTED" and not all(
            (self.repo_id, self.repo_owner, self.repo_name, self.default_branch)
        ):
            raise source_error("Kết nối kho lưu trữ thiếu thông tin dữ liệu cần thiết.")
        return self


@dataclass(frozen=True)
class ReferenceFact:
    project_id: UUID
    repo_id: str
    generation: int
    source_version: int
    link_type: str
    ref_id: str
    title: str | None
    status: str | None
    url: str | None
    is_verified: bool
    synced_at: datetime

    def validate(self):
        validate_version(self.generation)
        validate_version(self.source_version)
        if (
            not isinstance(self.project_id, UUID)
            or not isinstance(self.repo_id, str)
            or not self.repo_id
            or len(self.repo_id) > 100
            or self.link_type not in {"BRANCH", "COMMIT", "PULL_REQUEST"}
            or not isinstance(self.ref_id, str)
            or not self.ref_id
            or len(self.ref_id) > 300
            or self.is_verified is not True
            or not isinstance(self.synced_at, datetime)
            or self.synced_at.tzinfo is None
        ):
            raise source_error("Liên kết dữ liệu chưa được dịch vụ tích hợp xác nhận hợp lệ.")
        if self.title is not None and (not isinstance(self.title, str) or len(self.title) > 300):
            raise source_error("Tiêu đề từ nguồn tích hợp không hợp lệ.")
        if self.status is not None and (
            self.link_type != "PULL_REQUEST" or self.status not in {"OPEN", "MERGED", "CLOSED"}
        ):
            raise source_error("Trạng thái từ nguồn tích hợp không phù hợp với loại liên kết.")
        if self.link_type == "PULL_REQUEST" and (
            not self.ref_id.isascii()
            or not self.ref_id.isdecimal()
            or int(self.ref_id) < 1
            or str(int(self.ref_id)) != self.ref_id
        ):
            raise source_error("Mã định danh yêu cầu kéo (Pull Request) phải là số nguyên dương.")
        if self.url is not None:
            url = urlparse(self.url)
            if (
                len(self.url) > 1000
                or url.scheme != "https"
                or url.hostname != "github.com"
                or url.username
                or url.password
                or url.query
            ):
                raise source_error("Đường dẫn liên kết không hợp lệ.")
        return self


class UnavailableIntegration:
    def select_repository(self, **kwargs):
        raise source_error("Dịch vụ tích hợp hiện không khả dụng.")

    def verify_reference(self, **kwargs):
        raise source_error("Dịch vụ xác thực liên kết tích hợp hiện không khả dụng.")

    prepare = select_repository
    confirm = select_repository
    abort = select_repository
    status = select_repository


def integration_client():
    return import_string(settings.INTEGRATION_ADAPTER)()


@dataclass(frozen=True)
class AccountFact:
    user_id: UUID
    github_user_id: str
    github_username: str
    source_version: int
    verified: bool

    def validate(self):
        validate_version(self.source_version)
        if (
            not isinstance(self.user_id, UUID)
            or type(self.verified) is not bool
            or not self.github_user_id
            or len(self.github_user_id) > 100
            or not self.github_username
            or len(self.github_username) > 100
        ):
            raise source_error("Thông tin tài khoản tích hợp không hợp lệ.")
        return self


CONNECTION_FIELDS = frozenset(
    {
        "project_id",
        "operation_id",
        "generation",
        "source_version",
        "status",
        "repo_id",
        "repo_owner",
        "repo_name",
        "default_branch",
        "synced_at",
    }
)


def connection_fact_from_data(data):
    try:
        if not isinstance(data, dict) or set(data) != CONNECTION_FIELDS:
            raise ValueError()
        result = ConnectionFact(
            **{
                **data,
                "project_id": UUID(data["project_id"]),
                "synced_at": parse_datetime(data["synced_at"]),
            }
        )
        result.validate()
        if result.generation < 1 or result.source_version < 1:
            raise ValueError()
        if result.repo_id is not None and re.fullmatch(r"[1-9][0-9]{0,99}", result.repo_id) is None:
            raise ValueError()
        if result.status == "DISCONNECTED" and any(
            (result.repo_id, result.repo_owner, result.repo_name, result.default_branch)
        ):
            raise ValueError()
        return result
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        raise source_error("Invalid connection response") from exc


class RemoteIntegration:
    """The single HTTP boundary to Integration; all business decisions remain in Work."""

    def _request(self, method, path, *, bearer=None, body=None):
        base = settings.WORK_INTEGRATION_BASE_URL
        key = settings.WORK_INTEGRATION_SERVICE_KEY
        try:
            url = urlparse(base)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.path not in {"", "/"}
                or url.username
                or url.password
                or url.query
                or url.fragment
                or any(c.isspace() for c in base)
                or not isinstance(key, str)
                or not key.isascii()
                or not key.isprintable()
                or key.strip() != key
                or not 32 <= len(key) <= 4096
                or connection.in_atomic_block
            ):
                raise ValueError()
            _ = url.port
            headers = {"X-Service-Key": key, "Accept": "application/json"}
            if bearer is not None:
                parts = bearer.split()
                if len(parts) == 2 and parts[0].lower() == "bearer":
                    bearer = parts[1]
                if (
                    not bearer
                    or not bearer.isascii()
                    or len(bearer) > 8192
                    or any(ord(c) < 33 or ord(c) > 126 for c in bearer)
                ):
                    raise ValueError()
                headers["Authorization"] = "Bearer " + bearer
            with requests.request(
                method,
                base.rstrip("/") + path,
                headers=headers,
                json=body,
                # Provider verifies current access and metadata with sequential GitHub calls.
                timeout=(30, 30),
                allow_redirects=False,
                stream=True,
            ) as reply:
                if reply.status_code != 200:
                    status = reply.status_code
                    if status in {401, 403, 404, 409, 410, 422, 429}:
                        messages = {
                            401: "Phiên đăng nhập không còn hợp lệ. Vui lòng đăng nhập lại.",
                            403: "Bạn chưa được cấp quyền truy cập kho mã nguồn này.",
                            404: "Không tìm thấy dữ liệu GitHub được yêu cầu.",
                            409: "Kết nối kho mã nguồn đã thay đổi. Vui lòng tải lại dữ liệu.",
                            410: "Yêu cầu kết nối đã hết hạn. Vui lòng tạo yêu cầu mới.",
                            422: "Thông tin liên kết GitHub không hợp lệ. Vui lòng kiểm tra lại.",
                            429: "Có quá nhiều yêu cầu GitHub. Vui lòng thử lại sau.",
                        }
                        raise WorkError("INTEGRATION_" + str(status), messages[status], status)
                    raise ValueError()
                raw = bytearray()
                for chunk in reply.iter_content(4096):
                    raw.extend(chunk)
                    if len(raw) > 65536:
                        raise ValueError()
                envelope = json.loads(raw)
                if (
                    not isinstance(envelope, dict)
                    or envelope.get("success") is not True
                    or not isinstance(envelope.get("data"), dict)
                ):
                    raise ValueError()
                return envelope["data"]
        except (
            requests.RequestException,
            ValueError,
            TypeError,
            AttributeError,
            KeyError,
            RecursionError,
        ) as exc:
            raise source_error(type(exc).__name__) from None

    def _path(self, project_id):
        return f"/api/v1/internal/projects/{UUID(str(project_id))}/github/"

    def prepare(self, *, project_id, body, bearer):
        fact = connection_fact_from_data(
            self._request(
                "POST", self._path(project_id) + "connection/prepare", bearer=bearer, body=body
            )
        )
        if (
            fact.project_id != project_id
            or fact.operation_id != body["operation_id"]
            or fact.status != "PENDING"
            or fact.repo_id != body["github_repo_id"]
            or fact.generation != body["expected_generation"] + 1
        ):
            raise source_error("Prepare binding mismatch")
        return fact

    def confirm(self, *, project_id, operation_id, generation):
        return connection_fact_from_data(
            self._request(
                "POST",
                self._path(project_id) + "connection/confirm",
                body={"operation_id": operation_id, "generation": generation},
            )
        )

    def abort(self, *, project_id, operation_id, generation):
        return self._operation(
            self._request(
                "POST",
                self._path(project_id) + "connection/abort",
                body={"operation_id": operation_id, "generation": generation},
            ),
            project_id,
            operation_id,
        )

    def status(self, *, project_id, operation_id):
        return self._operation(
            self._request(
                "GET",
                self._path(project_id) + "connection/operations/" + quote(operation_id, safe=""),
            ),
            project_id,
            operation_id,
        )

    def _operation(self, data, project_id, operation_id):
        try:
            if (
                set(data)
                != {
                    "project_id",
                    "operation_id",
                    "action",
                    "state",
                    "generation",
                    "expires_at",
                    "result",
                }
                or data["project_id"] != str(project_id)
                or data["operation_id"] != operation_id
                or data["action"] not in {"CONNECT", "DISCONNECT"}
                or data["state"] not in {"PREPARED", "CONFIRMED", "ABORTED", "EXPIRED"}
                or type(data["generation"]) is not int
                or data["generation"] < 1
            ):
                raise ValueError()
            stamp = parse_datetime(data["expires_at"])
            if stamp is None or stamp.tzinfo is None:
                raise ValueError()
            if data["result"] is not None:
                fact = connection_fact_from_data(data["result"])
                if (
                    fact.project_id != project_id
                    or fact.operation_id != operation_id
                    or fact.generation != data["generation"]
                ):
                    raise ValueError()
            return data
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise source_error("Invalid operation response") from exc

    def verify_reference(
        self, *, project_id, repo_id, generation, link_type, github_ref_id, bearer, actor=None
    ):
        data = self._request(
            "POST",
            self._path(project_id) + "references/verify",
            bearer=bearer,
            body={
                "repo_id": repo_id,
                "generation": generation,
                "link_type": link_type,
                "ref_id": github_ref_id,
            },
        )
        try:
            fields = {
                "project_id",
                "repo_id",
                "generation",
                "source_version",
                "link_type",
                "ref_id",
                "title",
                "status",
                "url",
                "is_verified",
                "synced_at",
            }
            if set(data) != fields:
                raise ValueError()
            fact = ReferenceFact(
                **{
                    **data,
                    "project_id": UUID(data["project_id"]),
                    "synced_at": parse_datetime(data["synced_at"]),
                }
            )
            fact.validate()
            if (
                (fact.project_id, fact.repo_id, fact.generation, fact.link_type)
                != (project_id, repo_id, generation, link_type)
                or fact.generation < 1
                or fact.source_version < 1
            ):
                raise ValueError()
            if fact.url:
                parsed = urlparse(fact.url)
                if (
                    parsed.fragment
                    or parsed.port not in {None, 443}
                    or not parsed.path.startswith("/")
                ):
                    raise ValueError()
            return fact
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise source_error("Invalid reference response") from exc
