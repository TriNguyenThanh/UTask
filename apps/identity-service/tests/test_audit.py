import uuid

import pytest
from django.db import DatabaseError, transaction

from accounts.models import AuditLog

pytestmark = pytest.mark.integration


def _create_audit_log():
    return AuditLog.objects.create(
        actor_id=str(uuid.uuid4()),
        action="LOGIN_FAILED",
        target_user_id=str(uuid.uuid4()),
        ip_address="2001:db8::2",
        user_agent="Identity audit test",
        details={"reason": "invalid credentials", "attempt": 2},
    )


@pytest.mark.django_db
@pytest.mark.postgres
def test_audit_details_default_to_empty_object_and_have_no_secret_columns():
    log = AuditLog.objects.create(
        action="LOGIN_FAILED",
        ip_address="127.0.0.1",
        user_agent="Identity audit test",
    )

    assert log.details == {}
    field_names = {field.name for field in AuditLog._meta.get_fields()}
    assert field_names.isdisjoint(
        {
            "password",
            "password_hash",
            "refresh_token",
            "refresh_token_hash",
            "token",
            "token_hash",
            "secret",
        }
    )


@pytest.mark.django_db
@pytest.mark.postgres
@pytest.mark.parametrize("mutation", ["update", "delete"])
def test_audit_logs_reject_update_and_delete_with_sqlstate_p0001(mutation):
    log = _create_audit_log()

    with pytest.raises(DatabaseError) as error:
        with transaction.atomic():
            query = AuditLog.objects.filter(pk=log.pk)
            if mutation == "update":
                query.update(action="MODIFIED")
            else:
                query.delete()

    assert error.value.__cause__.sqlstate == "P0001"
    log.refresh_from_db()
    assert log.action == "LOGIN_FAILED"
