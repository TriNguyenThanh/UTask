import json
from pathlib import Path
from uuid import uuid4

import jsonschema
import pytest
from django.utils import timezone

from apps.courses.models import Enrollment
from apps.groups.models import GroupMember, StudyGroup
from apps.messaging.models import Activity, OutboxEvent

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]
EVENT_CONTRACT = Path(__file__).resolve().parents[4] / (
    "contracts/events/classroom.group.membership.changed.v1.json"
)


def _validate_membership_event(event):
    validator = jsonschema.Draft202012Validator(
        json.loads(EVENT_CONTRACT.read_text(encoding="utf-8")),
        format_checker=jsonschema.FormatChecker(),
    )
    validator.validate(event)


def test_enrollment_reactivate_endpoint_and_batch_flag(
    section, actors, client_for, post_command, identity
):
    teacher = client_for(actors["teacher"])
    student = client_for(actors["outsider"])
    enrollment = Enrollment.objects.get(class_section=section, user_id=actors["outsider"])
    enrollment.status = "REMOVED"
    enrollment.left_at = timezone.now()
    enrollment.save(update_fields=["status", "left_at"])

    # Student cannot self-reactivate
    denied = post_command(
        student,
        f"/classes/{section.pk}/enrollments/{enrollment.pk}/reactivate/",
        {"reason": "Xin vào lại"},
    )
    assert denied.status_code == 404

    # Closed class rejects reactivation
    section.status = "CLOSED"
    section.save(update_fields=["status"])
    closed = post_command(
        teacher,
        f"/classes/{section.pk}/enrollments/{enrollment.pk}/reactivate/",
        {"reason": "Khôi phục"},
    )
    assert closed.status_code == 409 and closed.json()["error"]["code"] == "CLASS_NOT_OPEN"
    section.status = "OPEN"
    section.save(update_fields=["status"])

    # Teacher reactivates successfully with idempotency replay
    key = uuid4()
    reactivated = post_command(
        teacher,
        f"/classes/{section.pk}/enrollments/{enrollment.pk}/reactivate/",
        {"reason": "Xóa nhầm sinh viên"},
        key,
    )
    assert reactivated.status_code == 200
    assert reactivated.json()["data"]["status"] == "ACTIVE"
    assert reactivated.json()["data"]["left_at"] is None
    assert (
        post_command(
            teacher,
            f"/classes/{section.pk}/enrollments/{enrollment.pk}/reactivate/",
            {"reason": "Xóa nhầm sinh viên"},
            key,
        ).json()
        == reactivated.json()
    )
    assert Activity.objects.filter(verb="enrollment.reactivated").count() == 1

    # Already active returns 409 ENROLLMENT_ALREADY_ACTIVE
    already = post_command(
        teacher,
        f"/classes/{section.pk}/enrollments/{enrollment.pk}/reactivate/",
        {"reason": "Khôi phục lại"},
    )
    assert already.status_code == 409
    assert already.json()["error"]["code"] == "ENROLLMENT_ALREADY_ACTIVE"

    # Batch student import with reactivate_inactive=True reactivates LEFT/REMOVED
    enrollment.status = "LEFT"
    enrollment.left_at = timezone.now()
    enrollment.save(update_fields=["status", "left_at"])
    identity["provision"] = lambda rows, k: {
        "results": [
            {
                "row_number": 1,
                "user_id": str(actors["outsider"]),
                "email": "student@example.test",
                "student_id": "SV01",
                "account_status": "ACTIVE",
                "account_result": "EXISTING",
                "reason": None,
            }
        ]
    }
    batch_resp = post_command(
        teacher,
        f"/classes/{section.pk}/students/",
        {
            "students": [{"row_number": 1, "email": "student@example.test", "student_id": "SV01"}],
            "reactivate_inactive": True,
        },
    )
    assert batch_resp.status_code == 200
    assert batch_resp.json()["data"]["summary"]["reactivated"] == 1
    assert batch_resp.json()["data"]["results"][0]["enrollment_result"] == "REACTIVATED"
    enrollment.refresh_from_db()
    assert enrollment.status == "ACTIVE"


@pytest.mark.parametrize("mode", ["leave", "remove", "adjust_none", "adjust_move", "exit"])
def test_sole_leader_dissolve_flow_across_all_four_commands(
    section, actors, client_for, post_command, mode
):
    solo_group = StudyGroup.objects.create(
        class_section=section,
        name="Nhóm 1 người",
        invite_code_hash="0" * 64,
        invite_expires_at=timezone.now(),
    )
    leader_enrollment = Enrollment.objects.get(class_section=section, user_id=actors["leader"])
    GroupMember.objects.create(
        class_section=section, group=solo_group, enrollment=leader_enrollment, role="LEADER"
    )
    target_group = None
    if mode == "adjust_move":
        target_group = StudyGroup.objects.create(class_section=section, name="Nhóm đích")
        GroupMember.objects.create(
            class_section=section,
            group=target_group,
            enrollment=Enrollment.objects.get(class_section=section, user_id=actors["member"]),
            role="LEADER",
        )

    teacher = client_for(actors["teacher"])
    leader = client_for(actors["leader"])

    if mode == "leave":
        route = f"/groups/{solo_group.pk}/leave/"
        client = leader
        base = {"version": 1, "reason": "Đổi nhóm"}
    elif mode == "remove":
        route = f"/groups/{solo_group.pk}/remove-member/"
        client = teacher
        base = {"version": 1, "user_id": str(actors["leader"]), "reason": "Giải tán nhóm"}
    elif mode in {"adjust_none", "adjust_move"}:
        route = f"/classes/{section.pk}/adjust-member/"
        client = teacher
        base = {
            "user_id": str(actors["leader"]),
            "target_group_id": str(target_group.pk) if target_group else None,
            "reason": "Điều chuyển",
        }
    else:
        route = f"/classes/{section.pk}/enrollments/{leader_enrollment.pk}/exit/"
        client = leader
        base = {"reason": "Rời lớp"}

    blocked = post_command(client, route, base)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "SOLE_LEADER_DISSOLVE_REQUIRED"

    dissolved = post_command(client, route, {**base, "dissolve_if_sole_member": True})
    assert dissolved.status_code == 200, dissolved.content

    solo_group.refresh_from_db()
    assert solo_group.status == "ARCHIVED"
    assert solo_group.invite_code_hash is None
    assert not GroupMember.objects.filter(group=solo_group, status="ACTIVE").exists()
    assert Activity.objects.filter(verb="group.dissolved", subject_id=solo_group.pk).exists()

    events = list(OutboxEvent.objects.filter(aggregate_id=solo_group.pk))
    assert len(events) == 1
    _validate_membership_event(events[0].data)
    assert events[0].data["data"]["group_status"] == "ARCHIVED"
    assert all(m["status"] != "ACTIVE" for m in events[0].data["data"]["members"])

    if mode == "adjust_move":
        assert GroupMember.objects.filter(
            group=target_group, enrollment=leader_enrollment, status="ACTIVE"
        ).exists()
    elif mode != "exit":
        # Former sole leader is now free to create a new group in the same class
        recreated = post_command(
            leader, "/groups/", {"class_id": str(section.pk), "name": "Nhóm mới"}
        )
        assert recreated.status_code == 201


def test_multi_member_leader_still_requires_successor_even_with_dissolve_flag(
    group, actors, client_for, post_command
):
    response = post_command(
        client_for(actors["leader"]),
        f"/groups/{group.pk}/leave/",
        {"version": 1, "reason": "Xin rời", "dissolve_if_sole_member": True},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "LEADER_SUCCESSOR_REQUIRED"


def test_archiving_group_requires_reason_releases_members_and_emits_event(
    group, actors, client_for, post_command
):
    teacher = client_for(actors["teacher"])
    path = f"/groups/{group.pk}/"

    missing_reason = teacher.patch(
        path,
        {"version": 1, "status": "ARCHIVED"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid4()),
    )
    assert missing_reason.status_code == 400
    assert missing_reason.json()["error"]["code"] == "VALIDATION_ERROR"

    archived = teacher.patch(
        path,
        {"version": 1, "status": "ARCHIVED", "reason": "Hợp nhất sang nhóm khác"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid4()),
    )
    assert archived.status_code == 200
    assert archived.json()["data"]["status"] == "ARCHIVED"
    assert archived.json()["data"]["member_count"] == 0
    assert archived.json()["data"]["leader_id"] is None

    group.refresh_from_db()
    assert group.invite_code_hash is None
    assert not GroupMember.objects.filter(group=group, status="ACTIVE").exists()
    assert GroupMember.objects.filter(group=group, status="REMOVED").count() == 2

    event = OutboxEvent.objects.get(aggregate_id=group.pk).data
    _validate_membership_event(event)
    assert event["data"]["group_status"] == "ARCHIVED"
    assert all(m["status"] == "REMOVED" for m in event["data"]["members"])

    # Released members can immediately create a new group in the same class
    new_group = post_command(
        client_for(actors["member"]),
        "/groups/",
        {"class_id": str(group.class_section_id), "name": "Nhóm mới sau lưu trữ"},
    )
    assert new_group.status_code == 201


def test_lock_grouping_preconditions_idempotency_and_unlock_grouping(
    group, actors, client_for, post_command
):
    section = group.class_section
    section.group_min_size = 3
    section.save(update_fields=["group_min_size"])
    teacher = client_for(actors["teacher"])

    # Has 1 unassigned student (outsider) AND 1 undersized group (2/3)
    unmet = post_command(teacher, f"/classes/{section.pk}/lock-grouping/", {"version": 1})
    assert unmet.status_code == 409
    assert unmet.json()["error"]["code"] == "GROUPING_PRECONDITIONS_UNMET"
    fields = {d["field"] for d in unmet.json()["error"]["details"]}
    assert "unassigned_students" in fields
    assert f"groups.{group.pk}" in fields

    # Force lock succeeds
    forced = post_command(
        teacher, f"/classes/{section.pk}/lock-grouping/", {"version": 1, "force": True}
    )
    assert forced.status_code == 200
    assert forced.json()["data"]["grouping_phase"] == "LOCKED"
    assert forced.json()["data"]["version"] == 2

    # Locking again with current version is idempotent and does NOT increment version
    repeat_lock = post_command(teacher, f"/classes/{section.pk}/lock-grouping/", {"version": 2})
    assert repeat_lock.status_code == 200
    assert repeat_lock.json()["data"]["version"] == 2

    # Unlock requires reason and resets grouping_phase to FORMING
    unlocked = post_command(
        teacher,
        f"/classes/{section.pk}/unlock-grouping/",
        {"version": 2, "reason": "Mở lại cho sinh viên bổ sung nhóm"},
    )
    assert unlocked.status_code == 200
    assert unlocked.json()["data"]["grouping_phase"] == "FORMING"
    assert unlocked.json()["data"]["grouping_locked_at"] is None
    assert unlocked.json()["data"]["version"] == 3
    assert Activity.objects.filter(verb="class.grouping_unlocked", subject_id=section.pk).exists()

    # Unlocking again when FORMING is idempotent and does NOT increment version
    repeat_unlock = post_command(
        teacher,
        f"/classes/{section.pk}/unlock-grouping/",
        {"version": 3, "reason": "Đã mở sẵn"},
    )
    assert repeat_unlock.status_code == 200
    assert repeat_unlock.json()["data"]["version"] == 3

    # Once outsider joins group (now 3/3 and 0 unassigned), lock without force succeeds
    GroupMember.objects.create(
        class_section=section,
        group=group,
        enrollment=Enrollment.objects.get(class_section=section, user_id=actors["outsider"]),
        role="MEMBER",
    )
    clean_lock = post_command(teacher, f"/classes/{section.pk}/lock-grouping/", {"version": 3})
    assert clean_lock.status_code == 200
    assert clean_lock.json()["data"]["grouping_phase"] == "LOCKED"
    assert clean_lock.json()["data"]["version"] == 4
