import hashlib
import json
import re
from uuid import UUID

from rest_framework.exceptions import ParseError

MAX_COUNTER = 9_223_372_036_854_775_806


def project_uuid(value):
    try:
        result = UUID(str(value))
        if result.int == 0:
            raise ValueError()
        return result
    except (ValueError, TypeError, AttributeError):
        raise ParseError("Project ID không hợp lệ.") from None


def operation_id(value):
    if (
        not isinstance(value, str)
        or value in {".", ".."}
        or not re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", value)
    ):
        raise ParseError("Operation ID không hợp lệ.")
    return value


def counter(value, *, minimum=0):
    if type(value) is not int or not minimum <= value <= MAX_COUNTER:
        raise ParseError("Generation không hợp lệ.")
    return value


def repository_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,99}", value):
        raise ParseError("Repository ID không hợp lệ.")
    return value


def prepare_payload(body):
    if not isinstance(body, dict) or set(body) != {
        "operation_id",
        "action",
        "expected_generation",
        "github_repo_id",
    }:
        raise ParseError("Payload prepare không hợp lệ.")
    operation_id(body["operation_id"])
    counter(body["expected_generation"])
    if body["action"] == "CONNECT":
        repository_id(body["github_repo_id"])
    elif body["action"] != "DISCONNECT" or body["github_repo_id"] is not None:
        raise ParseError("Action và repository không khớp.")
    return body


def command_payload(body):
    if not isinstance(body, dict) or set(body) != {"operation_id", "generation"}:
        raise ParseError("Payload operation không hợp lệ.")
    operation_id(body["operation_id"])
    counter(body["generation"], minimum=1)
    return body


def reference_payload(body):
    if not isinstance(body, dict) or set(body) != {"repo_id", "generation", "link_type", "ref_id"}:
        raise ParseError("Payload reference không hợp lệ.")
    repository_id(body["repo_id"])
    counter(body["generation"], minimum=1)
    if (
        body["link_type"] not in ("BRANCH", "COMMIT", "PULL_REQUEST")
        or not isinstance(body["ref_id"], str)
        or not 1 <= len(body["ref_id"]) <= 300
        or any(ord(char) < 32 or ord(char) == 127 for char in body["ref_id"])
    ):
        raise ParseError("Reference không hợp lệ.")
    if body["link_type"] == "COMMIT" and not re.fullmatch(r"[0-9a-fA-F]{7,40}", body["ref_id"]):
        raise ParseError("Mã thay đổi GitHub phải gồm 7–40 ký tự 0–9, a–f hoặc A–F.")
    return body


def payload_digest(body, user_id):
    canonical = json.dumps({**body, "actor": str(user_id)}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
