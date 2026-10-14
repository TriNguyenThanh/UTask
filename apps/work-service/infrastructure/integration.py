import logging
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse
from uuid import UUID

from django.conf import settings
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
