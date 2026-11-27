from types import SimpleNamespace
from uuid import uuid4

import pytest

from apps.courses.services import classes
from common.errors import ClassroomError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("denied_at", [None, "read", "manage", "open"])
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
    monkeypatch.setattr(
        classes,
        "get_object_or_404",
        lambda *args, **kwargs: SimpleNamespace(status="CLOSED" if denied_at == "open" else "OPEN"),
    )

    def guard(stage):
        def check(*args):
            events.append(stage)
            if denied_at == stage:
                raise ClassroomError("PERMISSION_DENIED", "Bạn không có quyền quản lý lớp.", 403)

        return check

    def verify(*args):
        events.append("identity")
        raise ClassroomError("IDENTITY_UNAVAILABLE", "Không thể xác minh tài khoản.", 503)

    def open_guard(section, **kwargs):
        events.append("open")
        if section.status != "OPEN":
            raise ClassroomError("CLASS_NOT_OPEN", "Lớp học hiện không mở.", 409)

    monkeypatch.setattr(classes, "require_read", guard("read"))
    monkeypatch.setattr(classes, "require_manage", guard("manage"))
    monkeypatch.setattr(classes, "require_open", open_guard)
    monkeypatch.setattr(classes, "verified_teacher", verify)
    with pytest.raises(ClassroomError) as error:
        classes.change_class(
            request,
            uuid4(),
            {"version": 1, "user_id": uuid4(), "role": "CO_TEACHER", "status": "ACTIVE"},
            action="teacher",
        )
    expected = ["read", "manage", "open", "identity"]
    if denied_at:
        expected = expected[: expected.index(denied_at) + 1]
    assert events == expected
    expected_status = 409 if denied_at == "open" else 403 if denied_at else 503
    assert error.value.status_code == expected_status
