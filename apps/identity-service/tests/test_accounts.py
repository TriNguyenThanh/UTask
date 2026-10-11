from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import (
    AccountStatus,
    GlobalRole,
    GlobalRoleCode,
    User,
    UserGlobalRole,
    UserProfile,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db, pytest.mark.postgres]


def test_create_user_normalizes_hashes_and_creates_profile_and_student_role():
    user = User.objects.create_user(
        email="  Student.One@Example.edu  ",
        username="  Student.One  ",
        password="SecurePass123!",
        student_id="  ab-123  ",
        first_name="Linh",
        last_name="Trần",
    )

    user.refresh_from_db()
    user.profile.refresh_from_db()
    assert user.email == "student.one@example.edu"
    assert user.username == "student.one"
    assert user.student_id == "AB-123"
    assert user.check_password("SecurePass123!")
    assert user.password != "SecurePass123!"
    assert user.profile.display_name == "Trần Linh"
    assert list(user.global_role_assignments.values_list("role__code", flat=True)) == [
        GlobalRoleCode.STUDENT
    ]


def test_blank_student_id_becomes_null_and_missing_password_is_unusable():
    user = User.objects.create_user(email="pending@example.edu", student_id="  ")

    assert user.student_id is None
    assert not user.has_usable_password()
    assert user.global_role_assignments.count() == 1


def test_generated_username_retries_real_postgres_unique_collision():
    User.objects.create_user(email="first@example.edu", username="member")
    manager = User.objects

    with mock.patch.object(manager, "_available_username", side_effect=["member", "member-2"]):
        user = manager.create_user(email="member@example.edu", password="SecurePass123!")

    assert user.username == "member-2"
    assert UserProfile.objects.filter(user=user).exists()
    assert UserGlobalRole.objects.filter(user=user, role__code=GlobalRoleCode.STUDENT).exists()


def test_user_profile_and_role_creation_roll_back_as_one_transaction():
    with mock.patch.object(
        UserGlobalRole.objects,
        "create",
        side_effect=RuntimeError("test role-write failure"),
    ):
        with pytest.raises(RuntimeError, match="test role-write failure"):
            User.objects.create_user(
                email="rollback@example.edu",
                password="SecurePass123!",
                first_name="Rollback",
            )

    assert not User.objects.filter(email="rollback@example.edu").exists()
    assert not UserProfile.objects.filter(user__email="rollback@example.edu").exists()
    assert not UserGlobalRole.objects.filter(user__email="rollback@example.edu").exists()


def test_missing_role_fails_without_silently_creating_a_role_or_user():
    with pytest.raises(GlobalRole.DoesNotExist):
        User.objects.create_user(
            email="unknown-role@example.edu",
            password="SecurePass123!",
            global_role_code="NOT_A_ROLE",
        )

    assert not User.objects.filter(email="unknown-role@example.edu").exists()
    assert GlobalRole.objects.count() == 3


def test_soft_deleted_email_and_student_id_remain_reserved():
    old_user = User.objects.create_user(
        email="reserved@example.edu",
        username="reserved",
        student_id="2026-ABC",
    )
    old_user.deleted_at = timezone.now()
    old_user.save(update_fields=("deleted_at", "updated_at"))

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            User.objects.create_user(email="reserved@example.edu", username="other")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            User.objects.create_user(
                email="other@example.edu",
                username="other-student",
                student_id="2026-ABC",
            )

    assert User.objects.filter(email="reserved@example.edu").count() == 1
    assert User.objects.filter(student_id="2026-ABC").count() == 1


@pytest.mark.parametrize(
    "updates",
    [
        {"email": "MixedCase@example.edu"},
        {"username": "MixedCase"},
        {"student_id": "lower-case"},
        {"account_status": "UNKNOWN"},
        {"account_status": "LOCKED"},
    ],
)
def test_database_checks_reject_invalid_identity_values(updates):
    user = User.objects.create_user(email="checks@example.edu", username="checks")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            User.objects.filter(pk=user.pk).update(**updates)


def test_database_checks_reject_global_role_code_outside_registry():
    role = GlobalRole.objects.get(code=GlobalRoleCode.STUDENT)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            GlobalRole.objects.filter(pk=role.pk).update(code="PROJECT_ADMIN")


def test_profile_display_name_trigger_handles_insert_and_name_updates():
    user = User.objects.create_user(
        email="profile@example.edu",
        first_name="Minh",
        last_name="Vũ",
    )
    profile = user.profile
    profile.refresh_from_db()
    assert profile.display_name == "Vũ Minh"

    UserProfile.objects.filter(pk=profile.pk).update(first_name="Lan")
    profile.refresh_from_db()
    assert profile.display_name == "Vũ Lan"

    empty_name_user = User.objects.create_user(email="empty-name@example.edu")
    empty_name_user.profile.refresh_from_db()
    assert empty_name_user.profile.display_name == "Thành viên UTask"


@pytest.mark.parametrize(
    ("account_status", "deleted", "expected"),
    [
        (AccountStatus.ACTIVE, False, True),
        (AccountStatus.PENDING_ACTIVATION, False, False),
        (AccountStatus.SUSPENDED, False, False),
        (AccountStatus.ACTIVE, True, False),
    ],
)
def test_is_active_reflects_status_and_soft_delete(account_status, deleted, expected):
    user = User.objects.create_user(email=f"{account_status.lower()}-{deleted}@example.edu")
    user.account_status = account_status
    user.deleted_at = timezone.now() if deleted else None
    user.save()

    user.refresh_from_db()
    assert user.is_active is expected
    assert "is_active" not in {field.name for field in User._meta.fields}


def test_role_seed_command_is_idempotent():
    call_command("seed_global_roles")
    call_command("seed_global_roles")

    assert GlobalRole.objects.count() == 3
    assert set(GlobalRole.objects.values_list("code", flat=True)) == set(GlobalRoleCode.values)


def test_bootstrap_command_creates_system_admin_only_and_never_prints_password():
    output = StringIO()
    with mock.patch(
        "accounts.management.commands.bootstrap_identity_admin.getpass.getpass",
        side_effect=["BootstrapAdmin123!", "BootstrapAdmin123!"],
    ):
        call_command(
            "bootstrap_identity_admin",
            email="admin@example.edu",
            username="site-admin",
            first_name="Site",
            last_name="Admin",
            stdout=output,
        )

    admin = User.objects.get(email="admin@example.edu")
    assert admin.check_password("BootstrapAdmin123!")
    assert list(admin.global_role_assignments.values_list("role__code", flat=True)) == [
        GlobalRoleCode.SYSTEM_ADMIN
    ]
    assert not hasattr(admin, "is_superuser")
    assert "BootstrapAdmin123!" not in output.getvalue()


@pytest.mark.parametrize(
    ("passwords", "message"),
    [
        (["weak", "weak"], "at least 8 characters"),
        (["BootstrapAdmin123!", "DifferentAdmin123!"], "did not match"),
    ],
)
def test_bootstrap_rejects_mismatched_or_weak_password_without_creating_user(passwords, message):
    with mock.patch(
        "accounts.management.commands.bootstrap_identity_admin.getpass.getpass",
        side_effect=passwords,
    ):
        with pytest.raises(CommandError, match=message):
            call_command(
                "bootstrap_identity_admin",
                email="admin@example.edu",
                username="site-admin",
            )

    assert not User.objects.filter(email="admin@example.edu").exists()
