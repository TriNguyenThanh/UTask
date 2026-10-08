"""Exercise old-to-new schema with legacy data in an isolated PostgreSQL test schema."""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

pytestmark = pytest.mark.integration


@pytest.mark.django_db(transaction=True)
def test_account_state_migration_fails_closed_then_preserves_library_data():
    assert connection.settings_dict["NAME"].startswith("test_")
    schema = "identity_migration_test_" + uuid4().hex
    quoted = connection.ops.quote_name(schema)
    with connection.cursor() as cursor:
        cursor.execute("SHOW search_path")
        original_path = cursor.fetchone()[0]
        cursor.execute(f"CREATE SCHEMA {quoted}")
        cursor.execute(f"SET search_path TO {quoted}")
    try:
        old_targets = [
            ("accounts", "0004_idempotencyrecord"),
            ("account", "0009_emailaddress_unique_primary_email"),
        ]
        executor = MigrationExecutor(connection)
        executor.migrate(old_targets)
        old_apps = executor.loader.project_state(old_targets).apps
        User = old_apps.get_model("accounts", "User")
        EmailAddress = old_apps.get_model("account", "EmailAddress")
        now = timezone.now()
        locked = User.objects.create(
            email="locked@example.edu.vn",
            username="locked",
            account_status="LOCKED",
            locked_until=now + timedelta(minutes=5),
            failed_login_attempts=5,
        )
        existing = User.objects.create(
            email="existing@example.edu.vn",
            username="existing",
            is_email_verified=True,
        )
        EmailAddress.objects.create(
            user=existing, email=existing.email, primary=True, verified=False
        )
        missing = User.objects.create(
            email="missing@example.edu.vn",
            username="missing",
            is_email_verified=True,
        )
        suspended = User.objects.create(
            email="suspended@example.edu.vn",
            username="suspended",
            account_status="SUSPENDED",
            deleted_at=now,
        )
        target = [("accounts", "0005_library_owned_account_state")]
        executor = MigrationExecutor(connection)
        with pytest.raises(RuntimeError, match="Unexpired legacy account locks"):
            executor.migrate(target)
        locked.refresh_from_db()
        assert locked.account_status == "LOCKED"
        assert not EmailAddress.objects.filter(user=missing).exists()
        User.objects.filter(pk=locked.pk).update(locked_until=now - timedelta(minutes=1))
        executor = MigrationExecutor(connection)
        executor.migrate(target)
        new_apps = executor.loader.project_state(target).apps
        NewUser = new_apps.get_model("accounts", "User")
        NewEmail = new_apps.get_model("account", "EmailAddress")
        assert NewUser.objects.get(pk=locked.pk).account_status == "ACTIVE"
        assert not NewEmail.objects.get(user_id=existing.pk).verified
        assert NewEmail.objects.get(user_id=missing.pk).verified
        preserved = NewUser.objects.get(pk=suspended.pk)
        assert preserved.account_status == "SUSPENDED" and preserved.deleted_at == now
        with connection.cursor() as cursor:
            columns = {
                c.name for c in connection.introspection.get_table_description(cursor, "users")
            }
        assert not columns & {"failed_login_attempts", "locked_until", "is_email_verified"}
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('search_path', %s, false)", [original_path])
            cursor.execute(f"DROP SCHEMA {quoted} CASCADE")
