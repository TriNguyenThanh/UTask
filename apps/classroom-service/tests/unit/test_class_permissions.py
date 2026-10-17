from types import SimpleNamespace
from uuid import uuid4

import pytest

from apps.courses.services import classes
from common.errors import ClassroomError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("denied_at", [None, "read", "manage"])
def test_teacher_assignment_checks_class_authority_before_identity_lookup(monkeypatch, denied_at):
    request = SimpleNamespace(
        classroom_roles={"TEACHER"},
        user=SimpleNamespace(id=uuid4()),
        method="POST",
        path="/classes/teachers/assign/",
        headers={"Idempotency-Key": str(uuid4())},
    )
    events = []
    monkeypatch.setattr(classes, "lookup_receipt", lambda *args: None)
    monkeypatch.setattr(classes, "get_object_or_404", lambda *args, **kwargs: object())

    def guard(stage):
        def check(*args):
            events.append(stage)
            if denied_at == stage:
                raise ClassroomError("PERMISSION_DENIED", "Bạn không có quyền quản lý lớp.", 403)

        return check

    def verify(*args):
        events.append("identity")
        raise ClassroomError("IDENTITY_UNAVAILABLE", "Không thể xác minh tài khoản.", 503)

    monkeypatch.setattr(classes, "require_read", guard("read"))
    monkeypatch.setattr(classes, "require_manage", guard("manage"))
    monkeypatch.setattr(classes, "verified_teacher", verify)
    with pytest.raises(ClassroomError) as error:
        classes.change_class(
            request,
            uuid4(),
            {"version": 1, "user_id": uuid4(), "role": "CO_TEACHER", "status": "ACTIVE"},
            action="teacher",
        )
    expected = ["read", "manage", "identity"]
    if denied_at:
        expected = expected[: expected.index(denied_at) + 1]
    assert events == expected
    assert error.value.status_code == (403 if denied_at else 503)
