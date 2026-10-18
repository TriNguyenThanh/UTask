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


@pytest.mark.parametrize("roles", [{"TEACHER"}, {"STUDENT"}, {"SYSTEM_ADMIN"}])
def test_visible_groups_reuses_class_scope_including_current_global_roles(monkeypatch, roles):
    class_manager, group_manager = Mock(), Mock()
    monkeypatch.setattr(classes.ClassSection, "objects", class_manager)
    monkeypatch.setattr(group_queries.StudyGroup, "objects", group_manager)
    monkeypatch.setattr(group_queries, "paginate", lambda *args, **kwargs: ([], {}))
    request = SimpleNamespace(
        user=SimpleNamespace(id=uuid4()), classroom_roles=roles, query_params={}
    )
    assert group_queries.visible_groups(request) == ([], {})
    class_qs = class_manager.all.return_value
    if "SYSTEM_ADMIN" in roles:
        group_manager.filter.assert_called_once_with(class_section__in=class_qs)
    else:
        criteria = str(class_qs.filter.call_args.args[0])
        assert ("teachers__" in criteria) is ("TEACHER" in roles)
        group_manager.filter.assert_called_once_with(
            class_section__in=class_qs.filter.return_value.distinct.return_value
        )


@pytest.mark.parametrize("admin_allowed", [False, True])
@pytest.mark.parametrize("guard", [groups.require_group_read, groups.require_leader])
def test_admin_group_access_requires_explicit_operation_opt_in(monkeypatch, admin_allowed, guard):
    monkeypatch.setattr(groups, "active_member", lambda *args: None)
    monkeypatch.setattr(groups, "is_teacher", lambda *args, **kwargs: False)
    group = SimpleNamespace(class_section=object())
    if admin_allowed:
        assert guard(group, object(), roles={"SYSTEM_ADMIN"}, admin_allowed=True) is None
    else:
        with pytest.raises(ClassroomError) as error:
            guard(group, object(), roles={"SYSTEM_ADMIN"})
        assert error.value.status_code in {403, 404}


@pytest.mark.parametrize(
    "member,teacher,allowed", [(True, False, True), (False, True, True), (False, False, False)]
)
def test_group_read_keeps_member_and_current_teacher_scope(monkeypatch, member, teacher, allowed):
    monkeypatch.setattr(groups, "active_member", lambda *args: member)
    monkeypatch.setattr(groups, "is_teacher", lambda *args, **kwargs: teacher)
    group = SimpleNamespace(class_section=object())
    if allowed:
        assert groups.require_group_read(group, object(), roles={"TEACHER"}) is None
    else:
        with pytest.raises(ClassroomError) as error:
            groups.require_group_read(group, object(), roles={"STUDENT"})
        assert error.value.status_code == 404


@pytest.mark.parametrize("roles", [{"TEACHER"}, {"STUDENT"}, {"SYSTEM_ADMIN"}])
def test_internal_teacher_groups_fail_closed_without_teacher_role(monkeypatch, roles):
    manager = Mock()
    group_id = uuid4()
    manager.filter.return_value.order_by.return_value.values_list.return_value = [group_id]
    monkeypatch.setattr(scope.StudyGroup, "objects", manager)
    result = scope.teacher_groups(SimpleNamespace(id=uuid4()), roles=roles)
    assert result == {"group_ids": [str(group_id)] if "TEACHER" in roles else []}
    assert manager.filter.called is ("TEACHER" in roles)


@pytest.mark.parametrize(
    "roles,assigned", [({"TEACHER"}, True), ({"STUDENT"}, True), ({"TEACHER"}, False)]
)
def test_feedback_scope_requires_current_teacher_role_and_assignment(monkeypatch, roles, assigned):
    group = SimpleNamespace(pk=uuid4(), class_section_id=uuid4(), source_version=2)
    section, actor = object(), SimpleNamespace(id=uuid4())
    monkeypatch.setattr(scope.transaction, "atomic", nullcontext)
    monkeypatch.setattr(scope, "get_object_or_404", lambda *args, **kwargs: group)
    monkeypatch.setattr(scope, "lock_class", lambda *args: section)
    teacher_manager, member_manager, links = Mock(), Mock(), Mock()
    teacher_manager.filter.return_value.exists.return_value = assigned
    teacher_manager.filter.return_value.values_list.return_value = [actor.id]
    member_manager.filter.return_value.values_list.return_value = []
    links.filter.return_value.exists.return_value = True
    monkeypatch.setattr(scope.ClassTeacher, "objects", teacher_manager)
    monkeypatch.setattr(scope.GroupMember, "objects", member_manager)
    monkeypatch.setattr(scope.GroupProjectLink, "objects", links)
    if "TEACHER" in roles and assigned:
        result = scope.feedback_scope(group.pk, actor, uuid4(), roles=roles)
        assert result["actor_id"] == str(actor.id)
        assert result["mentionable_user_ids"] == [str(actor.id)]
    else:
        with pytest.raises(ClassroomError) as error:
            scope.feedback_scope(group.pk, actor, uuid4(), roles=roles)
        assert error.value.status_code == 403
        links.filter.assert_not_called()


@pytest.mark.parametrize(
    "role,active_only", [("TEACHER", False), ("STUDENT", True), ("SYSTEM_ADMIN", False)]
)
def test_teacher_history_requires_current_teacher_or_admin_role(monkeypatch, role, active_only):
    request = SimpleNamespace(
        user=SimpleNamespace(id=uuid4()), classroom_roles={role}, query_params={}
    )
    teacher_manager = Mock()
    teacher_manager.filter.return_value.exists.return_value = True
    monkeypatch.setattr(classes.ClassTeacher, "objects", teacher_manager)
    monkeypatch.setattr(class_queries, "require_read", lambda *args: None)
    monkeypatch.setattr(class_queries, "paginate", lambda *args, **kwargs: ([], kwargs["scope"]))
    section = SimpleNamespace(pk=uuid4(), teachers=Mock())
    _, meta = class_queries.class_teachers(request, section)
    assert meta["active_only"] is active_only


@pytest.mark.parametrize(
    "query,admin_allowed",
    [
        (group_queries.group_detail, True),
        (group_queries.group_members, False),
        (group_queries.group_projects, False),
    ],
)
@pytest.mark.parametrize("allowed", [False, True])
def test_group_queries_pass_roles_with_operation_specific_admin_scope(
    monkeypatch, query, admin_allowed, allowed
):
    group = SimpleNamespace(pk=uuid4(), class_section=object())
    request = SimpleNamespace(
        user=SimpleNamespace(id=uuid4()), classroom_roles={"SYSTEM_ADMIN"}, query_params={}
    )
    monkeypatch.setattr(group_queries, "get_object_or_404", lambda *args, **kwargs: group)
    monkeypatch.setattr(group_queries.GroupMember, "objects", Mock())
    monkeypatch.setattr(group_queries.GroupProjectLink, "objects", Mock())
    calls = []

    def read(*args, **kwargs):
        calls.append(kwargs)
        if not allowed:
            raise ClassroomError("RESOURCE_NOT_FOUND", "Không tìm thấy nhóm.", 404)

    monkeypatch.setattr(group_queries, "require_group_read", read)
    monkeypatch.setattr(group_queries, "paginate", lambda *args, **kwargs: ([], {}))
    monkeypatch.setattr(
        group_queries, "GroupSerializer", lambda *args: SimpleNamespace(data={"id": str(group.pk)})
    )
    if allowed:
        query(request, group.pk)
    else:
        with pytest.raises(ClassroomError):
            query(request, group.pk)
    assert calls == [
        {"roles": {"SYSTEM_ADMIN"}, **({"admin_allowed": True} if admin_allowed else {})}
    ]


@pytest.mark.parametrize("allowed", [True, False])
def test_group_activity_guard_explicitly_allows_admin(monkeypatch, allowed):
    request = SimpleNamespace(
        user=SimpleNamespace(id=uuid4()), classroom_roles={"SYSTEM_ADMIN"}, query_params={}
    )
    section, group = SimpleNamespace(pk=uuid4()), SimpleNamespace(pk=uuid4())
    monkeypatch.setattr(activities.Activity, "objects", Mock())
    monkeypatch.setattr("django.shortcuts.get_object_or_404", lambda *args, **kwargs: group)
    monkeypatch.setattr(activities, "paginate", lambda *args, **kwargs: ([], {}))
    guard = Mock()
    if not allowed:
        guard.side_effect = ClassroomError("RESOURCE_NOT_FOUND", "Không tìm thấy nhóm.", 404)
    monkeypatch.setattr(activities, "require_group_read", guard)
    if allowed:
        assert activities.class_activities(request, section, group.pk) == ([], {})
    else:
        with pytest.raises(ClassroomError):
            activities.class_activities(request, section, group.pk)
    guard.assert_called_once_with(group, request.user, roles={"SYSTEM_ADMIN"}, admin_allowed=True)


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
