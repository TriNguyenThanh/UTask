from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import close_old_connections
from django.utils import timezone

from apps.courses.models import Enrollment
from apps.groups.models import GroupMember, StudyGroup
from apps.groups.services.members import change_member, join_group
from apps.messaging.models import IdempotencyRecord, OutboxEvent
from common.access_codes import code_hash
from common.errors import ClassroomError

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


@pytest.mark.postgres
def test_concurrent_students_cannot_claim_same_final_group_slot(group, actors, command_request):
    new_user = uuid4()
    Enrollment.objects.create(class_section=group.class_section, user_id=new_user)
    group.invite_code_hash = code_hash("FINAL123")
    group.invite_expires_at = timezone.now() + timedelta(days=1)
    group.save()
    barrier = Barrier(2)

    def attempt(user_id):
        close_old_connections()
        request = command_request(user_id, "/groups/join/")
        barrier.wait(timeout=10)
        try:
            return join_group(request, {"code": "FINAL123"}).status_code
        except ClassroomError as error:
            return error.code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, [new_user, actors["outsider"]]))
    assert sorted(map(str, results)) == ["201", "GROUP_FULL"]
    assert GroupMember.objects.filter(group=group, status="ACTIVE").count() == 3
    assert OutboxEvent.objects.count() == 1 and IdempotencyRecord.objects.count() == 1


def test_same_student_concurrently_joins_two_groups_only_once(group, actors, command_request):
    section = group.class_section
    target = StudyGroup.objects.create(class_section=section, name="Nhóm B")
    enrollment = Enrollment.objects.get(class_section=section, user_id=actors["member"])
    member = GroupMember.objects.get(enrollment=enrollment)
    member.status, member.left_at = "LEFT", timezone.now()
    member.save()
    GroupMember.objects.create(
        class_section=section, group=target, enrollment=enrollment, role="LEADER"
    )
    for study_group, code in ((group, "FIRST123"), (target, "SECOND12")):
        study_group.invite_code_hash = code_hash(code)
        study_group.invite_expires_at = timezone.now() + timedelta(days=1)
        study_group.save()
    barrier = Barrier(2)

    def attempt(code):
        close_old_connections()
        request = command_request(actors["outsider"], "/groups/join/")
        barrier.wait(timeout=10)
        try:
            return join_group(request, {"code": code}).status_code
        except ClassroomError as error:
            return error.code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ["FIRST123", "SECOND12"]))
    assert sorted(map(str, results)) == ["201", "ALREADY_IN_GROUP"]
    assert (
        GroupMember.objects.filter(enrollment__user_id=actors["outsider"], status="ACTIVE").count()
        == 1
    )


def test_concurrent_leader_transfers_keep_exactly_one_leader(group, actors, command_request):
    barrier = Barrier(2)

    def attempt(index):
        close_old_connections()
        request = command_request(actors["teacher"], f"/transfer/{index}/", roles=("TEACHER",))
        barrier.wait(timeout=10)
        try:
            return change_member(
                request,
                group.pk,
                {"version": 1, "user_id": actors["member"], "reason": "Phân công"},
                action="transfer-leader",
            ).status_code
        except ClassroomError as error:
            return error.code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, [1, 2]))
    assert sorted(map(str, results)) == ["200", "VERSION_CONFLICT"]
    assert GroupMember.objects.filter(group=group, status="ACTIVE", role="LEADER").count() == 1
