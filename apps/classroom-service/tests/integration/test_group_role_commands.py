from uuid import uuid4

import pytest
from django.db import connection
from django.utils import timezone

from apps.courses.models import Enrollment
from apps.groups.models import GroupMember, StudyGroup
from apps.groups.services.groups import create_group
from apps.groups.services.members import change_member
from apps.messaging.models import Activity, IdempotencyRecord, OutboxEvent
from common.errors import ClassroomError
from infrastructure.identity import IdentityClient

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize("actor,roles", [("teacher", ("TEACHER",)), ("admin", ("SYSTEM_ADMIN",))])
def test_manager_creates_group_for_enrolled_student_without_becoming_member(
    section, actors, command_request, monkeypatch, actor, roles
):
    calls = []

    def users(self, access, ids):
        assert not connection.in_atomic_block
        calls.append(ids)
        return [{"id": str(actors["leader"]), "roles": ["STUDENT"], "account_status": "ACTIVE"}]

    monkeypatch.setattr(IdentityClient, "users", users)
    request = command_request(actors[actor], "/groups/", roles=roles)
    payload = {"class_id": section.pk, "name": "Nhóm được phân công", "leader_id": actors["leader"]}
    response = create_group(request, payload)
    assert response.status_code == 201
    group = StudyGroup.objects.get(pk=response.data["data"]["id"])
    membership = GroupMember.objects.get(group=group)
    assert membership.enrollment.user_id == actors["leader"] and membership.role == "LEADER"
    assert not GroupMember.objects.filter(enrollment__user_id=actors[actor]).exists()
    assert create_group(request, payload).data == response.data
    assert calls == [[actors["leader"]]]
    assert OutboxEvent.objects.count() == Activity.objects.count() == 1
    with pytest.raises(ClassroomError) as duplicate:
        create_group(command_request(actors[actor], "/groups/", roles=roles), payload)
    assert duplicate.value.code == "ALREADY_IN_GROUP"
    request.classroom_roles = {"STUDENT"}
    with pytest.raises(ClassroomError):
        create_group(request, payload)
    assert OutboxEvent.objects.count() == 1


@pytest.mark.parametrize(
    "case,code",
    [
        ("inactive_account", "INVALID_GROUP_LEADER"),
        ("teacher_target", "INVALID_GROUP_LEADER"),
        ("inactive_enrollment", "ENROLLMENT_REQUIRED"),
        ("outside_class", "ENROLLMENT_REQUIRED"),
        ("locked", "GROUPING_LOCKED"),
        ("closed", "CLASS_NOT_OPEN"),
    ],
)
def test_create_on_behalf_keeps_account_enrollment_and_class_guards(
    section, actors, command_request, identity, case, code
):
    leader_id = uuid4() if case == "outside_class" else actors["leader"]
    identity["profiles"][str(leader_id)] = {
        "id": str(leader_id),
        "roles": ["TEACHER"] if case == "teacher_target" else ["STUDENT"],
        "account_status": "SUSPENDED" if case == "inactive_account" else "ACTIVE",
    }
    if case == "inactive_enrollment":
        Enrollment.objects.filter(class_section=section, user_id=leader_id).update(
            status="LEFT", left_at=timezone.now()
        )
    if case == "locked":
        section.grouping_phase = "LOCKED"
        section.grouping_locked_at = timezone.now()
        section.save()
    if case == "closed":
        section.status = "CLOSED"
        section.save()
    with pytest.raises(ClassroomError) as error:
        create_group(
            command_request(actors["admin"], "/groups/", roles=("SYSTEM_ADMIN",)),
            {"class_id": section.pk, "name": "Nhóm", "leader_id": leader_id},
        )
    assert error.value.code == code
    assert not StudyGroup.objects.exists()
    assert not GroupMember.objects.exists()
    assert not OutboxEvent.objects.exists()
    assert not IdempotencyRecord.objects.exists()


@pytest.mark.parametrize("actor,roles", [("teacher", ("TEACHER",)), ("admin", ("SYSTEM_ADMIN",))])
def test_manager_removes_member_after_grouping_lock_but_cannot_remove_leader(
    group, actors, command_request, actor, roles
):
    section = group.class_section
    section.grouping_phase = "LOCKED"
    section.grouping_locked_at = timezone.now()
    section.save()
    request = command_request(actors[actor], "/remove-member/", roles=roles)
    payload = {"version": 1, "user_id": actors["member"], "reason": "Điều chỉnh"}
    response = change_member(request, group.pk, payload, action="remove-member")
    assert response.status_code == 200
    assert change_member(request, group.pk, payload, action="remove-member").data == response.data
    assert (
        GroupMember.objects.get(group=group, enrollment__user_id=actors["member"]).status
        == "REMOVED"
    )
    with pytest.raises(ClassroomError) as error:
        change_member(
            command_request(actors[actor], "/remove-member/", roles=roles),
            group.pk,
            {"version": 2, "user_id": actors["leader"], "reason": "Loại trưởng nhóm"},
            action="remove-member",
        )
    assert error.value.code == "LEADER_SUCCESSOR_REQUIRED"
    assert OutboxEvent.objects.count() == 1
