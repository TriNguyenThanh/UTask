from contextlib import nullcontext


from types import SimpleNamespace


from unittest.mock import Mock


from uuid import uuid4


import pytest


from apps.courses import permissions as classes


from apps.courses.queries import classes as class_queries


from apps.courses.services import classes as class_commands


from apps.courses.services import enrollments


from apps.groups import permissions as groups


from apps.groups.queries import groups as group_queries


from apps.groups.queries import scope


from apps.groups.serializers.groups import GroupCreateSerializer


from apps.groups.services import groups as group_commands


from apps.groups.services import members


from apps.messaging.queries import activities


from common.errors import ClassroomError


pytestmark = pytest.mark.unit


@pytest.mark.parametrize("roles", [set(), {"STUDENT"}, {"SYSTEM_ADMIN"}, {"TEACHER"}])
@pytest.mark.parametrize("assigned", [False, True])
def test_teacher_requires_current_global_role_and_active_assignment(monkeypatch, roles, assigned):
    manager = Mock()
    manager.filter.return_value.exists.return_value = assigned
    monkeypatch.setattr(classes.ClassTeacher, "objects", manager)
    actor, section = SimpleNamespace(id=uuid4()), object()
    assert classes.is_teacher(actor, section, roles=roles) == ("TEACHER" in roles and assigned)
    if "TEACHER" in roles:
        manager.filter.assert_called_once_with(
            class_section=section, user_id=actor.id, status="ACTIVE"
        )
    else:
        manager.filter.assert_not_called()


@pytest.mark.parametrize(
    "roles,assigned,enrolled,read,manage",
    [
        ({"TEACHER"}, True, False, True, True),
        ({"STUDENT"}, True, False, False, False),
        ({"STUDENT"}, True, True, True, False),
        ({"TEACHER"}, False, False, False, False),
        ({"SYSTEM_ADMIN"}, False, False, True, True),
    ],
)
def test_class_read_and_manage_keep_current_role_scope(
    monkeypatch, roles, assigned, enrolled, read, manage
):
    teacher_manager, enrollment_manager = Mock(), Mock()
    teacher_manager.filter.return_value.exists.return_value = assigned
    enrollment_manager.filter.return_value.exists.return_value = enrolled
    monkeypatch.setattr(classes.ClassTeacher, "objects", teacher_manager)
    monkeypatch.setattr(classes.Enrollment, "objects", enrollment_manager)
    request = SimpleNamespace(user=SimpleNamespace(id=uuid4()), classroom_roles=roles)
    assert classes.can_read(request, object()) is read
    if manage:
        assert classes.require_manage(request, object()) is None
    else:
        with pytest.raises(ClassroomError, match="quản lý"):
            classes.require_manage(request, object())


@pytest.mark.parametrize("roles", [{"TEACHER"}, {"STUDENT"}, {"SYSTEM_ADMIN"}])
def test_visible_class_scope_drops_teacher_relation_after_role_revocation(monkeypatch, roles):
    manager = Mock()
    monkeypatch.setattr(classes.ClassSection, "objects", manager)
    request = SimpleNamespace(user=SimpleNamespace(id=uuid4()), classroom_roles=roles)
    result = classes.visible_classes(request)
    qs = manager.all.return_value
    if "SYSTEM_ADMIN" in roles:
        assert result is qs
        qs.filter.assert_not_called()
    else:
        criteria = str(qs.filter.call_args.args[0])
        assert ("teachers__" in criteria) is ("TEACHER" in roles)
        assert "enrollments__status" in criteria
        assert result is qs.filter.return_value.distinct.return_value


COMMANDS = [
    (class_commands, "create_class", "require_manage"),
    (class_commands, "change_class", "require_manage"),
    (class_commands, "issue_class_code", "require_manage"),
    (enrollments, "join_class", "require_role"),
    (enrollments, "add_students", "require_manage"),
    (enrollments, "exit_class", "require_manage"),
    (group_commands, "create_group", "require_manage"),
    (group_commands, "update_group", "require_leader"),
    (group_commands, "issue_invite_code", "require_leader"),
    (members, "join_group", "require_role"),
    (members, "change_member", "require_leader"),
    (members, "adjust_member", "require_manage"),
]
