"""Public in-process interface for Classroom and Work modules to query Identity."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from apps.accounts.models import User, UserGlobalRole
from apps.accounts.services.profiles import public_users
from apps.accounts.services.provisioning import provision_students as _provision_students


def _coerce_uuid(value: UUID | str) -> UUID | None:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _unique_uuids(user_ids: Iterable[UUID | str]) -> list[UUID]:
    ids: list[UUID] = []
    seen: set[UUID] = set()
    for raw in user_ids:
        uid = _coerce_uuid(raw)
        if uid is not None and uid not in seen:
            seen.add(uid)
            ids.append(uid)
    return ids


def get_user_roles(user_id: UUID | str) -> list[str]:
    uid = _coerce_uuid(user_id)
    if uid is None:
        return []
    return sorted(
        UserGlobalRole.objects.filter(
            user_id=uid,
            user__deleted_at__isnull=True,
        ).values_list("role__code", flat=True)
    )


def has_global_role(user_id: UUID | str, role_code: str) -> bool:
    uid = _coerce_uuid(user_id)
    if uid is None or not role_code:
        return False
    return UserGlobalRole.objects.filter(
        user_id=uid,
        user__deleted_at__isnull=True,
        role__code=role_code,
    ).exists()


def get_user_profiles(user_ids: Iterable[UUID | str]) -> dict[UUID, dict[str, Any]]:
    ids = _unique_uuids(user_ids)
    if not ids:
        return {}
    users = User.objects.filter(pk__in=ids, deleted_at__isnull=True).select_related("profile")
    result: dict[UUID, dict[str, Any]] = {}
    for user in users:
        profile = getattr(user, "profile", None)
        result[user.pk] = {
            "display_name": profile.display_name if profile is not None else "",
            "avatar_url": profile.avatar_url if profile is not None else None,
            "student_id": user.student_id,
            "email": user.email,
            "username": user.username,
            "github_username": profile.github_username if profile is not None else None,
        }
    return result


def get_users_batch(user_ids: Iterable[UUID | str]) -> list[dict[str, Any]]:
    ids = _unique_uuids(user_ids)
    if not ids:
        return []
    found = {user.pk: user for user in public_users().filter(pk__in=ids)}
    rows: list[dict[str, Any]] = []
    for uid in ids:
        user = found.get(uid)
        if user is None:
            continue
        profile = getattr(user, "profile", None)
        rows.append(
            {
                "id": str(user.pk),
                "email": user.email,
                "username": user.username,
                "student_id": user.student_id,
                "display_name": profile.display_name if profile is not None else "",
                "avatar_url": profile.avatar_url if profile is not None else None,
                "account_status": user.account_status,
                "roles": sorted(
                    assignment.role.code for assignment in user.global_role_assignments.all()
                ),
            }
        )
    return rows


def provision_students(
    actor,
    students: list[dict[str, Any]],
    *,
    idempotency_key: str,
    endpoint_path: str = "/api/v1/internal/users/provision-students",
) -> dict[str, Any]:
    _status, envelope = _provision_students(
        actor,
        students,
        idempotency_key,
        endpoint_path=endpoint_path,
    )
    return envelope["data"]
