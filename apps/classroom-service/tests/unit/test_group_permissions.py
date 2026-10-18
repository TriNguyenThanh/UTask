from types import SimpleNamespace

import pytest

from apps.groups import permissions
from common.errors import ClassroomError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "member_role,is_teacher,teacher_allowed,allowed",
    [
        ("LEADER", False, False, True),
        ("MEMBER", False, False, False),
        (None, True, False, False),
        (None, True, True, True),
        (None, False, True, False),
        (None, False, False, False),
    ],
)
def test_leader_permission_and_denial_message_follow_command_authority(
    monkeypatch, member_role, is_teacher, teacher_allowed, allowed
):
    member = SimpleNamespace(role=member_role) if member_role else None
    monkeypatch.setattr(permissions, "active_member", lambda *args: member)
    monkeypatch.setattr(permissions, "is_teacher", lambda *args, **kwargs: is_teacher)
    group = SimpleNamespace(class_section=object())
    if allowed:
        assert permissions.require_leader(group, object(), teacher_allowed=teacher_allowed) is None
    else:
        with pytest.raises(ClassroomError) as error:
            permissions.require_leader(group, object(), teacher_allowed=teacher_allowed)
        assert error.value.code == "LEADER_PERMISSION_REQUIRED"
        assert error.value.status_code == 403
        assert ("giảng viên" in str(error.value)) is teacher_allowed
