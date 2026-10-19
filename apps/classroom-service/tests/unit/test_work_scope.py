from contextlib import nullcontext
from types import SimpleNamespace
from uuid import uuid4

import pytest

from apps.groups.queries import scope
from common.errors import ClassroomError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "class_status,actor_present,can_read,expected_code",
    [
        ("OPEN", True, True, None),
        ("CLOSED", True, False, "RESOURCE_NOT_FOUND"),
        ("CLOSED", True, True, "CLASS_NOT_OPEN"),
        ("CLOSED", False, False, "CLASS_NOT_OPEN"),
    ],
)
def test_snapshot_checks_actor_scope_before_exposing_class_state(
    monkeypatch, class_status, actor_present, can_read, expected_code
):
    group = SimpleNamespace(pk=uuid4(), class_section_id=uuid4())
    section = SimpleNamespace(status=class_status)
    monkeypatch.setattr(scope.transaction, "atomic", nullcontext)
    monkeypatch.setattr(scope, "get_object_or_404", lambda *args, **kwargs: group)
    monkeypatch.setattr(scope, "lock_class", lambda *args: section)
    monkeypatch.setattr(scope, "membership_snapshot", lambda *args: {"source_version": 1})

    def read(*args, **kwargs):
        if not can_read:
            raise ClassroomError("RESOURCE_NOT_FOUND", "Không tìm thấy nhóm học tập.", 404)

    monkeypatch.setattr(scope, "require_group_read", read)
    actor = object() if actor_present else None
    if expected_code:
        with pytest.raises(ClassroomError) as error:
            scope.group_snapshot(group.pk, actor)
        assert error.value.code == expected_code
    else:
        assert scope.group_snapshot(group.pk, actor) == {"source_version": 1}
