from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from apps.courses.models import ClassTeacher, Enrollment
from apps.groups.models import GroupMember, StudyGroup
from apps.groups.queries.scope import membership_snapshot
from apps.groups.services.groups import issue_invite_code
from apps.groups.services.members import adjust_member, change_member, join_group
from apps.messaging.models import Activity, IdempotencyRecord, OutboxEvent
from common.access_codes import code_hash
from common.errors import ClassroomError

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


def test_invite_rotation_advances_version_and_rejects_stale_writer(group, actors, command_request):
    request = command_request(actors["leader"], "/invite/")
    payload = {"version": 1, "enabled": True}
    response = issue_invite_code(request, group.pk, payload)
    group.refresh_from_db()
    digest = group.invite_code_hash
    assert response.data["data"]["version"] == group.source_version == 2
    replay = issue_invite_code(request, group.pk, payload)
    assert replay.data["data"]["version"] == 2
    assert "code" not in replay.data["data"]
    with pytest.raises(ClassroomError) as error:
        issue_invite_code(command_request(actors["leader"], "/invite/"), group.pk, payload)
    assert error.value.code == "VERSION_CONFLICT"
    group.refresh_from_db()
    assert group.invite_code_hash == digest and group.source_version == 2
    assert Activity.objects.filter(verb="group.code.changed").count() == 1


def test_invitation_join_leave_rejoin_preserves_latest_state(group, actors, command_request):
    response = issue_invite_code(
        command_request(actors["leader"], "/invite/"), group.pk, {"version": 1, "enabled": True}
    )
    code = response.data["data"]["code"]
    group.refresh_from_db()
    assert group.invite_code_hash == code_hash(code)
    assert code not in str(list(IdempotencyRecord.objects.values("response_body")))
    assert code not in str(list(Activity.objects.values()))
    payload = {"code": code}
    request = command_request(actors["outsider"], "/groups/join/")
    assert join_group(request, payload).status_code == 201
    group.refresh_from_db()
    change_member(
        command_request(actors["outsider"], "/leave/"),
        group.pk,
        {"version": group.source_version, "reason": "Xin rời"},
        action="leave",
    )
    assert (
        join_group(command_request(actors["outsider"], "/groups/join/"), payload).status_code == 201
    )
    assert (
        GroupMember.objects.filter(group=group, enrollment__user_id=actors["outsider"]).count() == 2
    )
    group.refresh_from_db()
    snapshot = membership_snapshot(group)
    assert len(snapshot["members"]) == 3
    assert all(row["status"] == "ACTIVE" for row in snapshot["members"])
    assert OutboxEvent.objects.count() == 3


def test_teacher_adjusts_after_lock_preserving_successor_and_two_group_events(
    group, actors, command_request
):
    section = group.class_section
    section.grouping_phase = "LOCKED"
    section.grouping_locked_at = timezone.now()
    section.save()
    target = StudyGroup.objects.create(class_section=section, name="Nhóm B")
    enrollment = Enrollment.objects.get(class_section=section, user_id=actors["outsider"])
    GroupMember.objects.create(
        class_section=section, group=target, enrollment=enrollment, role="LEADER"
    )
    payload = {
        "user_id": actors["leader"],
        "target_group_id": target.pk,
        "successor_user_id": actors["member"],
        "reason": "Cân đối nhóm",
    }
    request = command_request(actors["teacher"], "/adjust/", roles=("TEACHER",))
    response = adjust_member(request, section.pk, payload)
    assert response.status_code == 200
    assert adjust_member(request, section.pk, payload).data == response.data
    assert (
        GroupMember.objects.get(group=group, status="ACTIVE").enrollment.user_id == actors["member"]
    )
    assert GroupMember.objects.get(group=group, status="ACTIVE").role == "LEADER"
    assert GroupMember.objects.filter(group=target, status="ACTIVE").count() == 2
    assert OutboxEvent.objects.count() == 2
    assert GroupMember.objects.filter(group=group, status="REMOVED").count() == 1


def test_teacher_assignment_removal_and_capacity_errors(group, actors, command_request):
    section = group.class_section

    def request():
        return command_request(actors["teacher"], "/adjust/", roles=("TEACHER",))

    payload = {"user_id": actors["outsider"], "target_group_id": group.pk, "reason": "Phân nhóm"}
    assert adjust_member(request(), section.pk, payload).status_code == 200
    extra = uuid4()
    Enrollment.objects.create(class_section=section, user_id=extra)
    with pytest.raises(ClassroomError) as full:
        adjust_member(request(), section.pk, {**payload, "user_id": extra})
    assert full.value.code == "GROUP_FULL"
    assert (
        adjust_member(request(), section.pk, {**payload, "target_group_id": None}).status_code
        == 200
    )
    with pytest.raises(ClassroomError) as leader:
        adjust_member(
            request(), section.pk, {**payload, "user_id": actors["leader"], "target_group_id": None}
        )
    assert leader.value.code == "LEADER_SUCCESSOR_REQUIRED"
    assert GroupMember.objects.filter(group=group, role="LEADER", status="ACTIVE").count() == 1


def test_group_join_replay_survives_revoked_code_but_requires_membership(
    group, actors, command_request
):
    group.invite_code_hash, group.invite_expires_at = (
        code_hash("OLDGROUP"),
        timezone.now() + timedelta(days=1),
    )
    group.save()
    request = command_request(actors["outsider"], "/groups/join/")
    payload = {"code": "OLDGROUP"}
    response = join_group(request, payload)
    group.invite_code_hash = None
    group.save()
    assert join_group(request, payload).data == response.data


def test_assignment_replay_rejects_lost_write_authority(group, actors, command_request):
    payload = {"user_id": actors["outsider"], "target_group_id": group.pk, "reason": "Phân công"}
    request = command_request(actors["teacher"], "/adjust/", roles=("TEACHER",))
    adjust_member(request, group.class_section_id, payload)
    Enrollment.objects.filter(class_section=group.class_section, user_id=actors["outsider"]).update(
        status="LEFT", left_at=timezone.now()
    )
    ClassTeacher.objects.filter(
        class_section=group.class_section, user_id=actors["teacher"]
    ).update(status="LEFT", left_at=timezone.now())
    Enrollment.objects.create(class_section=group.class_section, user_id=actors["teacher"])
    with pytest.raises(ClassroomError) as denied:
        adjust_member(request, group.class_section_id, payload)
    assert denied.value.status_code == 403
