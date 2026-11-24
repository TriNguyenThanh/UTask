from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import close_old_connections
from django.utils import timezone

from apps.courses.models import ClassTeacher, Enrollment
from apps.groups.models import GroupJoinRequest, GroupMember, GroupTopicProposal, StudyGroup
from apps.groups.services.join_requests import approve_join_request, create_join_request
from apps.groups.services.members import change_member, join_group
from apps.groups.services.topics import review_group_topic
from apps.messaging.models import Activity, IdempotencyRecord, OutboxEvent
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


@pytest.mark.postgres
def test_concurrent_join_request_approvals_cannot_exceed_group_max_size(
    group, actors, command_request
):
    section = group.class_section
    group.is_recruiting = True
    group.save(update_fields=["is_recruiting"])
    extra_user = uuid4()
    enr1 = Enrollment.objects.get(class_section=section, user_id=actors["outsider"])
    enr2 = Enrollment.objects.create(class_section=section, user_id=extra_user)
    req1 = GroupJoinRequest.objects.create(
        class_section=section, group=group, enrollment=enr1, user_id=actors["outsider"]
    )
    req2 = GroupJoinRequest.objects.create(
        class_section=section, group=group, enrollment=enr2, user_id=extra_user
    )
    barrier = Barrier(2)

    def attempt(req_id):
        close_old_connections()
        request = command_request(
            actors["leader"], f"/groups/{group.pk}/join-requests/{req_id}/approve/"
        )
        barrier.wait(timeout=10)
        try:
            return approve_join_request(request, group.pk, req_id, {"review_note": ""}).status_code
        except ClassroomError as error:
            return error.code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, [req1.pk, req2.pk]))
    assert sorted(map(str, results)) == ["200", "GROUP_FULL"]
    assert GroupMember.objects.filter(group=group, status="ACTIVE").count() == 3
    statuses = sorted(GroupJoinRequest.objects.filter(group=group).values_list("status", flat=True))
    assert statuses == ["APPROVED", "PENDING"]
    assert OutboxEvent.objects.filter(event_type="classroom.group.membership.changed").count() == 1


@pytest.mark.postgres
def test_concurrent_join_request_creates_enforce_single_pending_per_class(
    group, actors, command_request
):
    section = group.class_section
    group.is_recruiting = True
    group.save(update_fields=["is_recruiting"])
    lead_b = uuid4()
    enr_b = Enrollment.objects.create(class_section=section, user_id=lead_b)
    group_b = StudyGroup.objects.create(
        class_section=section, name="Nhóm Cạnh Tranh", is_recruiting=True
    )
    GroupMember.objects.create(
        class_section=section, group=group_b, enrollment=enr_b, role="LEADER"
    )
    barrier = Barrier(2)

    def attempt(target_group_id):
        close_old_connections()
        request = command_request(actors["outsider"], f"/groups/{target_group_id}/join-requests/")
        barrier.wait(timeout=10)
        try:
            return create_join_request(request, target_group_id, {"message": "Xin vào"}).status_code
        except ClassroomError as error:
            return error.code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, [group.pk, group_b.pk]))
    assert sorted(map(str, results)) == ["201", "PENDING_JOIN_REQUEST_EXISTS"]
    assert (
        GroupJoinRequest.objects.filter(
            class_section=section, user_id=actors["outsider"], status="PENDING"
        ).count()
        == 1
    )


@pytest.mark.postgres
def test_concurrent_topic_reviews_allow_only_one_decision(group, actors, command_request):
    section = group.class_section
    co_teacher = uuid4()
    ClassTeacher.objects.create(
        class_section=section, user_id=co_teacher, role="CO_TEACHER", status="ACTIVE"
    )
    proposal = GroupTopicProposal.objects.create(
        class_section=section,
        group=group,
        title="Đề tài đồng thời",
        summary="Kiểm tra khóa lạc quan khi 2 giảng viên duyệt cùng lúc",
        status="PENDING",
        submitted_by_user_id=actors["leader"],
        submitted_at=timezone.now(),
        version=2,
    )
    barrier = Barrier(2)

    def attempt(item):
        teacher_id, decision, feedback = item
        close_old_connections()
        request = command_request(
            teacher_id, f"/groups/{group.pk}/topic/review/", roles=("TEACHER",)
        )
        barrier.wait(timeout=10)
        try:
            return review_group_topic(
                request,
                group.pk,
                {"decision": decision, "feedback": feedback, "version": 2},
            ).status_code
        except ClassroomError as error:
            return error.code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                attempt,
                [
                    (actors["teacher"], "APPROVED", "Đạt"),
                    (co_teacher, "REVISION_REQUESTED", "Cần sửa"),
                ],
            )
        )
    assert sorted(map(str, results)) == ["200", "VERSION_CONFLICT"]
    proposal.refresh_from_db()
    assert proposal.version == 3
    assert proposal.status in {"APPROVED", "REVISION_REQUESTED"}
    assert (
        Activity.objects.filter(
            subject_type="GroupTopicProposal",
            subject_id=proposal.pk,
            verb="group.topic.reviewed",
        ).count()
        == 1
    )
