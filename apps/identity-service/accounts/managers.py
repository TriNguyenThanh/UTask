from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.contrib.auth.base_user import BaseUserManager
from django.db import IntegrityError, transaction
from django.utils.text import slugify

PROFILE_FIELDS = {
    "avatar_url",
    "phone_number",
    "bio",
    "github_username",
    "academic_year",
    "faculty",
    "timezone",
    "preferences",
}


def _constraint_name(error: IntegrityError) -> str | None:
    diagnostics = getattr(error.__cause__, "diag", None)
    return getattr(diagnostics, "constraint_name", None)


class UserManager(BaseUserManager):
    use_in_migrations = True

    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def normalize_username(username: str | None) -> str | None:
        if username is None:
            return None
        normalized = username.strip().lower()
        return normalized or None

    @staticmethod
    def normalize_student_id(student_id: str | None) -> str | None:
        if student_id is None:
            return None
        normalized = student_id.strip().upper()
        return normalized or None

    def _available_username(self, email: str) -> str:
        base = slugify(email.partition("@")[0]) or "user"
        attempt = 1
        while True:
            suffix = "" if attempt == 1 else f"-{attempt}"
            candidate = f"{base[: 100 - len(suffix)]}{suffix}"
            if not self.model._default_manager.filter(username=candidate).exists():
                return candidate
            attempt += 1

    def create_user(
        self,
        email: str,
        password: str | None = None,
        username: str | None = None,
        student_id: str | None = None,
        *,
        first_name: str = "",
        last_name: str = "",
        profile_fields: Mapping[str, Any] | None = None,
        global_role_code: str = "STUDENT",
        **extra_fields: Any,
    ):
        from accounts.models import GlobalRole, UserGlobalRole, UserProfile

        if not isinstance(email, str) or not email.strip():
            raise ValueError("An email address is required.")

        normalized_email = self.normalize_email(email)
        normalized_username = self.normalize_username(username)
        normalized_student_id = self.normalize_student_id(student_id)
        generated_username = normalized_username is None
        profile_values = dict(profile_fields or {})
        unknown_profile_fields = profile_values.keys() - PROFILE_FIELDS
        if unknown_profile_fields:
            fields = ", ".join(sorted(unknown_profile_fields))
            raise ValueError(f"Unsupported profile fields: {fields}.")

        user = self.model(
            email=normalized_email,
            username=normalized_username or self._available_username(normalized_email),
            student_id=normalized_student_id,
            **extra_fields,
        )
        if password is None:
            user.set_unusable_password()
        else:
            user.set_password(password)

        with transaction.atomic():
            while True:
                try:
                    # A savepoint permits retrying a concurrent slug collision
                    # without splitting user/profile/role creation.
                    with transaction.atomic():
                        user.save(force_insert=True)
                    break
                except IntegrityError as error:
                    if not generated_username or _constraint_name(error) != "uq_users_username":
                        raise
                    user.username = self._available_username(normalized_email)

            UserProfile.objects.create(
                user=user,
                first_name=first_name,
                last_name=last_name,
                **profile_values,
            )
            role = GlobalRole.objects.get(code=global_role_code)
            UserGlobalRole.objects.create(user=user, role=role)

        return user

    def create_superuser(
        self,
        email: str,
        password: str | None = None,
        username: str | None = None,
        **extra_fields: Any,
    ):
        if not password:
            raise ValueError("A password is required to create a SYSTEM_ADMIN account.")
        if extra_fields.pop("is_superuser", False) or extra_fields.pop("is_staff", False):
            raise ValueError("Django superuser/staff bypass flags are not supported.")
        return self.create_user(
            email=email,
            password=password,
            username=username,
            global_role_code="SYSTEM_ADMIN",
            **extra_fields,
        )
