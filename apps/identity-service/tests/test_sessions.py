import uuid
from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from accounts.models import SessionRevocationReason, User, UserSession

pytestmark = pytest.mark.integration


def _create_user():
    user_id = uuid.uuid4().hex
    return User.objects.create_user(
        email=f"session-{user_id}@example.edu",
        username=f"session-{user_id}",
    )


def _create_session(user, *, token_family=None, token_hash=None, **updates):
    values = {
        "user": user,
        "token_family": token_family or uuid.uuid4(),
        "refresh_token_hash": token_hash or uuid.uuid4().hex + uuid.uuid4().hex,
        "ip_address": "2001:db8::1",
        "user_agent": "Identity session test",
        "expires_at": timezone.now() + timedelta(days=1),
    }
    values.update(updates)
    return UserSession.objects.create(**values)


def _sqlstate(error):
    return error.value.__cause__.sqlstate


@pytest.mark.django_db
@pytest.mark.postgres
def test_only_one_live_session_per_family_and_rotation_retains_old_row():
    """DB uniqueness allows historical revoked rows; live rotation updates one stable row.

    This exercises the constraint directly, not the runtime rotation algorithm (test_rotation).
    """
    user = _create_user()
    family = uuid.uuid4()
    old_session = _create_session(user, token_family=family, token_hash="a" * 64)

    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            _create_session(user, token_family=family, token_hash="b" * 64)

    assert _sqlstate(error) == "23505"

    old_session.is_revoked = True
    old_session.revoked_at = timezone.now()
    old_session.revoked_reason = SessionRevocationReason.ROTATED
    old_session.save(update_fields=("is_revoked", "revoked_at", "revoked_reason"))
    child = _create_session(user, token_family=family, token_hash="b" * 64)

    assert UserSession.objects.filter(token_family=family).count() == 2
    assert UserSession.objects.filter(token_family=family, is_revoked=False).get() == child
    assert UserSession.objects.get(pk=old_session.pk).refresh_token_hash == "a" * 64


@pytest.mark.django_db
@pytest.mark.postgres
def test_refresh_token_hash_is_unique_across_sessions():
    user = _create_user()
    _create_session(user, token_hash="c" * 64)

    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            _create_session(user, token_hash="c" * 64)

    assert _sqlstate(error) == "23505"


@pytest.mark.django_db
@pytest.mark.postgres
@pytest.mark.parametrize(
    "case", ["invalid-expiry", "missing-revocation-fields", "not-revoked", "unknown-reason"]
)
def test_session_checks_reject_invalid_expiry_revocation_and_reason(case):
    user = _create_user()
    updates = {
        "invalid-expiry": {"expires_at": F("created_at")},
        "missing-revocation-fields": {"is_revoked": True},
        "not-revoked": {"revoked_at": timezone.now()},
        "unknown-reason": {
            "is_revoked": True,
            "revoked_at": timezone.now(),
            "revoked_reason": "UNKNOWN",
        },
    }[case]

    session = _create_session(user)
    with pytest.raises(IntegrityError) as error:
        with transaction.atomic():
            UserSession.objects.filter(pk=session.pk).update(**updates)
    assert _sqlstate(error) == "23514"
    session.refresh_from_db()
    assert session.is_revoked is False
    assert session.revoked_at is None
    assert session.revoked_reason is None
    assert session.expires_at > session.created_at
