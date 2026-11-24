from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from django.db import IntegrityError, connection, transaction
from rest_framework.test import APIRequestFactory

from apps.courses.models import ClassSection, ClassTeacher, Enrollment
from apps.groups.models import GroupJoinRequest, GroupMember, StudyGroup
from apps.groups.queries.profiles import fetch_user_profiles
from apps.messaging.models import OutboxEvent
from common.errors import ClassroomError
from infrastructure.identity import IdentityClient

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

FORBIDDEN_CLIENT_TERMS = (
    "Traceback",
    "SQL",
    "Classroom",
    "This field",
    "Ensure this",
    "Not found",
    "mock",
)


def _assert_vietnamese_error(response, expected_status, expected_code=None):
    assert response.status_code == expected_status
    body = response.json()
    assert body["success"] is False and body["data"] is None
    if expected_code is not None:
        assert body["error"]["code"] == expected_code
    texts = [body["message"], *(item.get("issue", "") for item in body["error"]["details"])]
    for text in texts:
        assert text and all(term not in text for term in FORBIDDEN_CLIENT_TERMS), text


def _enroll(section, user_id, *, status="ACTIVE", left_at=None):
    return Enrollment.objects.create(
        class_section=section,
        user_id=user_id,
        status=status,
        left_at=left_at,
    )


def test_class_formation_deadline_and_group_recruitment_fields(
    section, group, actors, client_for, post_command
):
    teacher = client_for(actors["teacher"])
    leader = client_for(actors["leader"])
    deadline = "2026-06-15T16:59:59Z"

    patch_class = teacher.patch(
        f"/classes/{section.pk}/",
        {"version": 1, "formation_deadline": deadline},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid4()),
    )
    assert patch_class.status_code == 200
    assert patch_class.json()["data"]["formation_deadline"] == deadline

    clear_deadline = teacher.patch(
        f"/classes/{section.pk}/",
        {"version": 2, "formation_deadline": None},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid4()),
    )
    assert clear_deadline.status_code == 200
    assert clear_deadline.json()["data"]["formation_deadline"] is None

    patch_group = leader.patch(
        f"/groups/{group.pk}/",
        {
            "version": 1,
            "is_recruiting": True,
            "recruitment_note": "Cần thêm bạn làm Backend và QA",
            "needed_skills": [" Python ", "React", "python", "PostgreSQL"],
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid4()),
    )
    assert patch_group.status_code == 200
    data = patch_group.json()["data"]
    assert data["is_recruiting"] is True
    assert data["recruitment_note"] == "Cần thêm bạn làm Backend và QA"
    assert data["needed_skills"] == ["Python", "React", "PostgreSQL"]

    too_many = leader.patch(
        f"/groups/{group.pk}/",
        {"version": 2, "needed_skills": [f"Skill{i}" for i in range(11)]},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid4()),
    )
    assert too_many.status_code == 400
    assert too_many.json()["error"]["code"] == "VALIDATION_ERROR"

    blank_skill = leader.patch(
        f"/groups/{group.pk}/",
        {"version": 2, "needed_skills": ["   "]},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid4()),
    )
    assert blank_skill.status_code == 400

    # Create group directly with recruitment fields
    new_leader_id = uuid4()
    _enroll(section, new_leader_id)
    created = post_command(
        client_for(new_leader_id),
        "/groups/",
        {
            "class_id": str(section.pk),
            "name": "Nhóm B",
            "is_recruiting": True,
            "recruitment_note": "Tìm UI/UX",
            "needed_skills": ["Figma", "figma"],
        },
    )
    assert created.status_code == 201
    assert created.json()["data"]["is_recruiting"] is True
    assert created.json()["data"]["needed_skills"] == ["Figma"]


def test_open_groups_filtering_privacy_cursor_query_budget_and_identity_fallback(
    section, group, actors, client_for, identity, django_assert_num_queries, monkeypatch
):
    # Configure identities with extra sensitive fields that MUST NOT leak
    identity["profiles"][str(actors["leader"])] = {
        "id": str(actors["leader"]),
        "display_name": "Nguyễn Trưởng Nhóm",
        "student_id": "22020001",
        "avatar_url": "https://cdn.example.test/a1.png",
        "email": "secret-leader@example.test",
        "roles": ["STUDENT"],
        "account_status": "ACTIVE",
    }

    # Group 1 (fixture): 2/3 members, recruiting, skills Python/React
    group.is_recruiting = True
    group.recruitment_note = "Cần bạn làm React frontend"
    group.needed_skills = ["React", "TypeScript"]
    group.save(update_fields=["is_recruiting", "recruitment_note", "needed_skills"])

    # Group 2: recruiting & open (1/3 members), skill Django
    leader2 = uuid4()
    _enroll(section, leader2)
    group2 = StudyGroup.objects.create(
        class_section=section,
        name="Nhóm Backend",
        is_recruiting=True,
        recruitment_note="Tuyển thành viên viết API",
        needed_skills=["Django", "PostgreSQL"],
    )
    GroupMember.objects.create(
        class_section=section,
        group=group2,
        enrollment=Enrollment.objects.get(class_section=section, user_id=leader2),
        role="LEADER",
    )

    # Group 3: recruiting BUT FULL (3/3 members) -> MUST BE EXCLUDED
    full_leaders = [uuid4(), uuid4(), uuid4()]
    for uid in full_leaders:
        _enroll(section, uid)
    full_group = StudyGroup.objects.create(
        class_section=section,
        name="Nhóm Đã Đầy",
        is_recruiting=True,
        needed_skills=["React"],
    )
    for idx, uid in enumerate(full_leaders):
        GroupMember.objects.create(
            class_section=section,
            group=full_group,
            enrollment=Enrollment.objects.get(class_section=section, user_id=uid),
            role="LEADER" if idx == 0 else "MEMBER",
        )

    # Group 4: NOT recruiting -> MUST BE EXCLUDED
    closed_leader = uuid4()
    _enroll(section, closed_leader)
    closed_group = StudyGroup.objects.create(
        class_section=section, name="Nhóm Đóng Tuyển", is_recruiting=False
    )
    GroupMember.objects.create(
        class_section=section,
        group=closed_group,
        enrollment=Enrollment.objects.get(class_section=section, user_id=closed_leader),
        role="LEADER",
    )

    # Group 5: ARCHIVED -> MUST BE EXCLUDED
    StudyGroup.objects.create(
        class_section=section, name="Nhóm Lưu Trữ", status="ARCHIVED", is_recruiting=True
    )

    # Outsider student creates a PENDING request on group2
    outsider_enrollment = Enrollment.objects.get(class_section=section, user_id=actors["outsider"])
    GroupJoinRequest.objects.create(
        class_section=section,
        group=group2,
        enrollment=outsider_enrollment,
        user_id=actors["outsider"],
        status="PENDING",
    )

    student = client_for(actors["outsider"])
    with django_assert_num_queries(5):
        res = student.get(f"/classes/{section.pk}/open-groups/")
    assert res.status_code == 200
    rows = res.json()["data"]
    assert len(rows) == 2
    by_id = {row["id"]: row for row in rows}
    assert set(by_id) == {str(group.pk), str(group2.pk)}
    assert by_id[str(group.pk)]["member_count"] == 2
    assert by_id[str(group.pk)]["max_size"] == 3
    assert by_id[str(group.pk)]["my_request_status"] is None
    assert by_id[str(group2.pk)]["my_request_status"] == "PENDING"
    assert set(by_id[str(group.pk)]["leader_profile"]) == {
        "user_id",
        "display_name",
        "student_id",
        "avatar_url",
    }
    assert by_id[str(group.pk)]["leader_profile"]["display_name"] == "Nguyễn Trưởng Nhóm"
    assert by_id[str(group.pk)]["leader_profile"]["student_id"] == "22020001"
    assert "email" not in by_id[str(group.pk)]["leader_profile"]

    # Case-insensitive skill filter
    by_skill = student.get(f"/classes/{section.pk}/open-groups/?skill=react")
    assert by_skill.status_code == 200
    assert [row["id"] for row in by_skill.json()["data"]] == [str(group.pk)]

    # Search filter matches recruitment_note
    by_search = student.get(f"/classes/{section.pk}/open-groups/?search=viết API")
    assert by_search.status_code == 200
    assert [row["id"] for row in by_search.json()["data"]] == [str(group2.pk)]

    # Pagination & cursor scope binding
    page1 = student.get(f"/classes/{section.pk}/open-groups/?page_size=1")
    assert page1.status_code == 200
    assert page1.json()["meta"]["pagination"]["has_next"] is True
    cursor = page1.json()["meta"]["pagination"]["next_cursor"]
    page2 = student.get(f"/classes/{section.pk}/open-groups/?page_size=1&cursor={cursor}")
    assert page2.status_code == 200
    assert page2.json()["data"][0]["id"] != page1.json()["data"][0]["id"]
    mismatch = student.get(
        f"/classes/{section.pk}/open-groups/?page_size=1&skill=react&cursor={cursor}"
    )
    assert mismatch.status_code == 400

    # Teacher & Admin can read (my_request_status=None); non-enrolled & LEFT student get 404
    assert (
        client_for(actors["teacher"]).get(f"/classes/{section.pk}/open-groups/").status_code == 200
    )
    assert client_for(actors["admin"]).get(f"/classes/{section.pk}/open-groups/").status_code == 200
    non_enrolled = uuid4()
    assert client_for(non_enrolled).get(f"/classes/{section.pk}/open-groups/").status_code == 404
    left_student = uuid4()
    _enroll(section, left_student, status="LEFT", left_at=datetime.now(UTC))
    assert client_for(left_student).get(f"/classes/{section.pk}/open-groups/").status_code == 404

    # Graceful Identity outage degradation
    def boom(self, token, ids):
        raise ClassroomError("IDENTITY_UNAVAILABLE", "Không thể lấy thông tin tài khoản.", 503)

    monkeypatch.setattr(IdentityClient, "users", boom)
    degraded = student.get(f"/classes/{section.pk}/open-groups/")
    assert degraded.status_code == 200
    assert degraded.json()["data"][0]["leader_profile"]["display_name"] is None


def test_unassigned_students_enforces_lh09_minimal_projection_and_excludes_inactive(
    section, group, actors, client_for, identity, django_assert_num_queries
):
    # Extra unassigned student who was previously REMOVED from `group` -> MUST appear
    now = datetime.now(UTC)
    removed_member_id = uuid4()
    removed_enrollment = _enroll(section, removed_member_id)
    GroupMember.objects.create(
        class_section=section,
        group=group,
        enrollment=removed_enrollment,
        role="MEMBER",
        status="REMOVED",
        joined_at=now,
        left_at=now,
    )

    # LEFT & REMOVED class enrollments -> MUST NOT appear
    left_student = uuid4()
    _enroll(section, left_student, status="LEFT", left_at=datetime.now(UTC))
    removed_student = uuid4()
    _enroll(section, removed_student, status="REMOVED", left_at=datetime.now(UTC))

    identity["profiles"][str(actors["outsider"])] = {
        "id": str(actors["outsider"]),
        "display_name": "Trần Bạn Học",
        "student_id": "22020099",
        "avatar_url": "https://cdn.example.test/s99.png",
        "email": "private-student@example.test",
        "roles": ["STUDENT"],
        "account_status": "ACTIVE",
    }

    student = client_for(actors["outsider"])
    # LH09 guard: students still CANNOT access full enrollments list
    assert student.get(f"/classes/{section.pk}/enrollments/").status_code == 403

    with django_assert_num_queries(4):
        res = student.get(f"/classes/{section.pk}/unassigned-students/")
    assert res.status_code == 200
    rows = res.json()["data"]
    returned_ids = {row["user_id"] for row in rows}
    assert returned_ids == {str(actors["outsider"]), str(removed_member_id)}
    for row in rows:
        assert set(row) == {"user_id", "display_name", "student_id", "avatar_url"}
        assert "enrollment_id" not in row
        assert "email" not in row
        assert "source" not in row
        assert "enrolled_at" not in row
        assert "left_at" not in row

    # Pagination works
    page1 = student.get(f"/classes/{section.pk}/unassigned-students/?page_size=1")
    assert page1.status_code == 200
    assert page1.json()["meta"]["pagination"]["has_next"] is True
    page2 = student.get(
        f"/classes/{section.pk}/unassigned-students/"
        f"?page_size=1&cursor={page1.json()['meta']['pagination']['next_cursor']}"
    )
    assert page2.status_code == 200
    assert page2.json()["data"][0]["user_id"] != page1.json()["data"][0]["user_id"]

    # Non-enrolled & LEFT student get 404
    assert client_for(uuid4()).get(f"/classes/{section.pk}/unassigned-students/").status_code == 404
    assert (
        client_for(left_student).get(f"/classes/{section.pk}/unassigned-students/").status_code
        == 404
    )


def test_join_request_create_list_approve_reject_cancel_and_guards(
    section, group, actors, client_for, post_command
):
    leader = client_for(actors["leader"])
    member = client_for(actors["member"])
    outsider = client_for(actors["outsider"])
    teacher = client_for(actors["teacher"])
    admin = client_for(actors["admin"])

    # Cannot request when group is NOT recruiting
    not_recruiting = post_command(
        outsider, f"/groups/{group.pk}/join-requests/", {"message": "Cho mình vào với"}
    )
    assert not_recruiting.status_code == 409
    assert not_recruiting.json()["error"]["code"] == "GROUP_NOT_RECRUITING"

    # Enable recruiting
    group.is_recruiting = True
    group.save(update_fields=["is_recruiting"])

    # Create another open group in the same class to test single-PENDING-per-class guard
    other_leader = uuid4()
    _enroll(section, other_leader)
    other_group = StudyGroup.objects.create(
        class_section=section, name="Nhóm Khác", is_recruiting=True
    )
    GroupMember.objects.create(
        class_section=section,
        group=other_group,
        enrollment=Enrollment.objects.get(class_section=section, user_id=other_leader),
        role="LEADER",
    )

    # Student already in a group cannot create request
    already = post_command(member, f"/groups/{other_group.pk}/join-requests/", {})
    assert already.status_code == 409
    assert already.json()["error"]["code"] == "ALREADY_IN_GROUP"

    # Teacher cannot create join request
    assert post_command(teacher, f"/groups/{group.pk}/join-requests/", {}).status_code == 403

    # Outsider creates join request (with idempotency replay)
    idem_key = uuid4()
    created = post_command(
        outsider, f"/groups/{group.pk}/join-requests/", {"message": "Mình biết React"}, key=idem_key
    )
    assert created.status_code == 201
    req_id = created.json()["data"]["id"]
    assert created.json()["data"]["status"] == "PENDING"
    assert created.json()["data"]["group_name"] == "Nhóm A"

    replayed = post_command(
        outsider, f"/groups/{group.pk}/join-requests/", {"message": "Mình biết React"}, key=idem_key
    )
    assert replayed.status_code == 201 and replayed.json()["data"]["id"] == req_id

    # Second PENDING request in same class (even for another group!) -> 409
    dup = post_command(outsider, f"/groups/{other_group.pk}/join-requests/", {})
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "PENDING_JOIN_REQUEST_EXISTS"

    # Permissions on GET /groups/<id>/join-requests/
    assert leader.get(f"/groups/{group.pk}/join-requests/").status_code == 200
    assert teacher.get(f"/groups/{group.pk}/join-requests/?status=PENDING").status_code == 200
    assert admin.get(f"/groups/{group.pk}/join-requests/").status_code == 200
    assert member.get(f"/groups/{group.pk}/join-requests/").status_code == 403
    assert outsider.get(f"/groups/{group.pk}/join-requests/").status_code == 404
    assert leader.get(f"/groups/{group.pk}/join-requests/?status=BOGUS").status_code == 400

    # Student views own join requests; teacher without enrollment gets 403
    mine = outsider.get(f"/classes/{section.pk}/my-join-requests/")
    assert mine.status_code == 200 and len(mine.json()["data"]) == 1
    assert mine.json()["data"][0]["id"] == req_id
    assert teacher.get(f"/classes/{section.pk}/my-join-requests/").status_code == 403

    # Leader cannot cancel student's request; student cancels own request
    assert (
        post_command(leader, f"/groups/{group.pk}/join-requests/{req_id}/cancel/", {}).status_code
        == 403
    )
    cancelled = post_command(outsider, f"/groups/{group.pk}/join-requests/{req_id}/cancel/", {})
    assert cancelled.status_code == 200 and cancelled.json()["data"]["status"] == "CANCELLED"

    # Re-cancelling or approving a cancelled request -> 409 JOIN_REQUEST_NOT_PENDING
    assert (
        post_command(leader, f"/groups/{group.pk}/join-requests/{req_id}/approve/", {}).json()[
            "error"
        ]["code"]
        == "JOIN_REQUEST_NOT_PENDING"
    )

    # Student creates new request -> Leader rejects with review_note
    req2 = post_command(outsider, f"/groups/{group.pk}/join-requests/", {"message": "Thử lại"})
    assert req2.status_code == 201
    req2_id = req2.json()["data"]["id"]
    rejected = post_command(
        leader,
        f"/groups/{group.pk}/join-requests/{req2_id}/reject/",
        {"review_note": "Nhóm cần kỹ năng backend hơn"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["data"]["status"] == "REJECTED"
    assert rejected.json()["data"]["review_note"] == "Nhóm cần kỹ năng backend hơn"

    # Student creates 3rd request -> regular MEMBER cannot approve (403); Leader approves (200)
    req3 = post_command(outsider, f"/groups/{group.pk}/join-requests/", {"message": "Làm backend"})
    assert req3.status_code == 201
    req3_id = req3.json()["data"]["id"]
    assert (
        post_command(member, f"/groups/{group.pk}/join-requests/{req3_id}/approve/", {}).status_code
        == 403
    )
    outbox_before = OutboxEvent.objects.filter(
        event_type="classroom.group.membership.changed", aggregate_id=group.pk
    ).count()
    approved = post_command(
        leader,
        f"/groups/{group.pk}/join-requests/{req3_id}/approve/",
        {"review_note": "Chào mừng bạn vào nhóm"},
    )
    assert approved.status_code == 200
    assert approved.json()["data"]["status"] == "APPROVED"
    assert GroupMember.objects.filter(
        group=group, enrollment__user_id=actors["outsider"], status="ACTIVE", role="MEMBER"
    ).exists()
    group.refresh_from_db()
    assert group.source_version == 2
    assert (
        OutboxEvent.objects.filter(
            event_type="classroom.group.membership.changed", aggregate_id=group.pk
        ).count()
        == outbox_before + 1
    )

    # Group is now full (3/3) -> another unassigned student cannot request (409 GROUP_FULL)
    extra_student = uuid4()
    _enroll(section, extra_student)
    full_err = post_command(client_for(extra_student), f"/groups/{group.pk}/join-requests/", {})
    assert full_err.status_code == 409 and full_err.json()["error"]["code"] == "GROUP_FULL"


def test_join_request_approve_blocks_when_group_becomes_full(
    section, group, actors, client_for, post_command
):
    group.is_recruiting = True
    group.save(update_fields=["is_recruiting"])
    extra_student = uuid4()
    _enroll(section, extra_student)

    req1 = post_command(client_for(actors["outsider"]), f"/groups/{group.pk}/join-requests/", {})
    req2 = post_command(client_for(extra_student), f"/groups/{group.pk}/join-requests/", {})
    assert req1.status_code == 201 and req2.status_code == 201

    leader = client_for(actors["leader"])
    ok = post_command(
        leader, f"/groups/{group.pk}/join-requests/{req1.json()['data']['id']}/approve/", {}
    )
    assert ok.status_code == 200
    # Now group has 3/3 members -> approving req2 must fail with 409 GROUP_FULL
    conflict = post_command(
        leader, f"/groups/{group.pk}/join-requests/{req2.json()['data']['id']}/approve/", {}
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "GROUP_FULL"
    assert GroupJoinRequest.objects.get(pk=req2.json()["data"]["id"]).status == "PENDING"


def test_pending_join_requests_auto_cancel_on_all_lifecycle_events(
    section, group, actors, client_for, post_command
):
    teacher = client_for(actors["teacher"])
    leader = client_for(actors["leader"])
    group.is_recruiting = True
    group.save(update_fields=["is_recruiting"])

    # 1) Student creates a new group -> auto-cancels their pending request
    s1 = uuid4()
    _enroll(section, s1)
    r1 = post_command(client_for(s1), f"/groups/{group.pk}/join-requests/", {}).json()["data"]["id"]
    new_grp = post_command(
        client_for(s1), "/groups/", {"class_id": str(section.pk), "name": "Nhóm Tự Tạo"}
    )
    assert new_grp.status_code == 201
    assert GroupJoinRequest.objects.get(pk=r1).status == "CANCELLED"

    # 2) Student joins another group via invite code -> auto-cancels their pending request
    s2 = uuid4()
    _enroll(section, s2)
    r2 = post_command(client_for(s2), f"/groups/{group.pk}/join-requests/", {}).json()["data"]["id"]
    code_resp = post_command(
        client_for(s1),
        f"/groups/{new_grp.json()['data']['id']}/invite-code/",
        {"version": 1, "enabled": True},
    )
    assert code_resp.status_code == 200
    joined = post_command(
        client_for(s2), "/groups/join/", {"code": code_resp.json()["data"]["code"]}
    )
    assert joined.status_code == 201
    assert GroupJoinRequest.objects.get(pk=r2).status == "CANCELLED"

    # 3) Teacher adjusts student into a group -> auto-cancels pending request
    s3 = uuid4()
    _enroll(section, s3)
    r3 = post_command(client_for(s3), f"/groups/{group.pk}/join-requests/", {}).json()["data"]["id"]
    adj = post_command(
        teacher,
        f"/classes/{section.pk}/adjust-member/",
        {
            "user_id": str(s3),
            "target_group_id": new_grp.json()["data"]["id"],
            "reason": "Phân công bổ sung",
        },
    )
    assert adj.status_code == 200
    assert GroupJoinRequest.objects.get(pk=r3).status == "CANCELLED"

    # 4) Student exits class -> auto-cancels pending request
    s4 = uuid4()
    e4 = _enroll(section, s4)
    r4 = post_command(client_for(s4), f"/groups/{group.pk}/join-requests/", {}).json()["data"]["id"]
    exited = post_command(
        client_for(s4), f"/classes/{section.pk}/enrollments/{e4.pk}/exit/", {"reason": "Rút môn"}
    )
    assert exited.status_code == 200
    assert GroupJoinRequest.objects.get(pk=r4).status == "CANCELLED"

    # 5) Archiving group -> auto-cancels pending requests targeting that group
    s5 = uuid4()
    _enroll(section, s5)
    r5 = post_command(client_for(s5), f"/groups/{group.pk}/join-requests/", {}).json()["data"]["id"]
    archived = leader.patch(
        f"/groups/{group.pk}/",
        {"version": 1, "status": "ARCHIVED", "reason": "Giải tán nhóm"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid4()),
    )
    assert archived.status_code == 200
    assert archived.json()["data"]["is_recruiting"] is False
    assert GroupJoinRequest.objects.get(pk=r5).status == "CANCELLED"

    # 6) Dissolving sole-leader group -> auto-cancels pending requests targeting that group
    sole_leader = uuid4()
    _enroll(section, sole_leader)
    solo_grp = post_command(
        client_for(sole_leader),
        "/groups/",
        {"class_id": str(section.pk), "name": "Nhóm Đơn", "is_recruiting": True},
    ).json()["data"]
    r6 = post_command(client_for(s5), f"/groups/{solo_grp['id']}/join-requests/", {}).json()[
        "data"
    ]["id"]
    dissolved = post_command(
        client_for(sole_leader),
        f"/groups/{solo_grp['id']}/leave/",
        {"version": 1, "reason": "Đổi ý", "dissolve_if_sole_member": True},
    )
    assert dissolved.status_code == 200
    assert GroupJoinRequest.objects.get(pk=r6).status == "CANCELLED"

    # 7) Class lock-grouping -> auto-cancels all pending requests in class
    recruiting_grp = post_command(
        client_for(sole_leader),
        "/groups/",
        {"class_id": str(section.pk), "name": "Nhóm Mới", "is_recruiting": True},
    ).json()["data"]
    r7 = post_command(client_for(s5), f"/groups/{recruiting_grp['id']}/join-requests/", {}).json()[
        "data"
    ]["id"]
    locked = post_command(
        teacher, f"/classes/{section.pk}/lock-grouping/", {"version": 1, "force": True}
    )
    assert locked.status_code == 200
    assert GroupJoinRequest.objects.get(pk=r7).status == "CANCELLED"

    # 8) Unlock grouping, create request, then CLOSE class -> auto-cancels pending request
    post_command(
        teacher, f"/classes/{section.pk}/unlock-grouping/", {"version": 2, "reason": "Mở lại"}
    )
    r8 = post_command(client_for(s5), f"/groups/{recruiting_grp['id']}/join-requests/", {}).json()[
        "data"
    ]["id"]
    closed = post_command(
        teacher, f"/classes/{section.pk}/state/", {"version": 3, "status": "CLOSED"}
    )
    assert closed.status_code == 200
    assert GroupJoinRequest.objects.get(pk=r8).status == "CANCELLED"


def test_join_request_postgres_unique_and_same_class_fk_constraints(section, group, actors):
    outsider_enrollment = Enrollment.objects.get(class_section=section, user_id=actors["outsider"])
    GroupJoinRequest.objects.create(
        class_section=section,
        group=group,
        enrollment=outsider_enrollment,
        user_id=actors["outsider"],
        status="PENDING",
    )
    # Partial unique constraint blocks 2nd PENDING for same (class_section, enrollment)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            GroupJoinRequest.objects.create(
                class_section=section,
                group=group,
                enrollment=outsider_enrollment,
                user_id=actors["outsider"],
                status="PENDING",
            )

    # Same-class composite FK blocks referencing a group from another class
    other_section = ClassSection.objects.create(
        course=section.course,
        code="SE02",
        name="Lớp SE 2",
        term="2026",
        starts_on=date(2026, 1, 1),
        ends_on=date(2026, 12, 31),
    )
    other_group = StudyGroup.objects.create(class_section=other_section, name="Nhóm Lớp Khác")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            GroupJoinRequest.objects.create(
                class_section=section,
                group=other_group,
                enrollment=outsider_enrollment,
                user_id=actors["outsider"],
                status="CANCELLED",
            )
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_open_groups_latest_my_request_status_dynamic_reappearance_and_profile_chunking(
    section, group, actors, client_for, post_command, identity
):
    group.is_recruiting = True
    group.save(update_fields=["is_recruiting"])
    outsider = client_for(actors["outsider"])
    leader = client_for(actors["leader"])
    member = client_for(actors["member"])

    # Multiple historical requests to SAME group: REJECTED -> CANCELLED -> PENDING
    r1 = post_command(outsider, f"/groups/{group.pk}/join-requests/", {}).json()["data"]["id"]
    post_command(leader, f"/groups/{group.pk}/join-requests/{r1}/reject/", {})
    r2 = post_command(outsider, f"/groups/{group.pk}/join-requests/", {}).json()["data"]["id"]
    post_command(outsider, f"/groups/{group.pk}/join-requests/{r2}/cancel/", {})
    r3 = post_command(outsider, f"/groups/{group.pk}/join-requests/", {}).json()["data"]["id"]

    og = outsider.get(f"/classes/{section.pk}/open-groups/").json()["data"]
    assert len(og) == 1 and og[0]["my_request_status"] == "PENDING"
    post_command(leader, f"/groups/{group.pk}/join-requests/{r3}/reject/", {})
    og_after = outsider.get(f"/classes/{section.pk}/open-groups/").json()["data"]
    assert og_after[0]["my_request_status"] == "REJECTED"

    # Full group disappears from open-groups, then reappears when a member leaves
    r4 = post_command(outsider, f"/groups/{group.pk}/join-requests/", {}).json()["data"]["id"]
    assert (
        post_command(leader, f"/groups/{group.pk}/join-requests/{r4}/approve/", {}).status_code
        == 200
    )
    assert outsider.get(f"/classes/{section.pk}/open-groups/").json()["data"] == []

    leave = post_command(member, f"/groups/{group.pk}/leave/", {"version": 2, "reason": "Đổi nhóm"})
    assert leave.status_code == 200
    reappeared = member.get(f"/classes/{section.pk}/open-groups/").json()["data"]
    assert [row["id"] for row in reappeared] == [str(group.pk)]

    # Archiving group frees remaining members back into unassigned-students
    arch = leader.patch(
        f"/groups/{group.pk}/",
        {"version": 3, "status": "ARCHIVED", "reason": "Giải tán nhóm"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid4()),
    )
    assert arch.status_code == 200
    unassigned_ids = {
        row["user_id"]
        for row in outsider.get(f"/classes/{section.pk}/unassigned-students/").json()["data"]
    }
    assert {str(actors["leader"]), str(actors["member"]), str(actors["outsider"])} <= unassigned_ids

    # fetch_user_profiles chunks >100 IDs safely into batches of <=100
    identity["calls"].clear()
    req = APIRequestFactory().get("/", HTTP_AUTHORIZATION="Bearer dummy-token")
    ids = [uuid4() for _ in range(105)]
    profiles = fetch_user_profiles(req, ids)
    assert len(profiles) == 105
    user_calls = [batch for kind, batch in identity["calls"] if kind == "users"]
    assert [len(batch) for batch in user_calls] == [100, 5]


def test_join_request_teacher_admin_roles_revoked_teacher_cross_group_and_idempotency(
    section, group, actors, client_for, post_command, identity
):
    group.is_recruiting = True
    group.save(update_fields=["is_recruiting"])

    co_teacher_id = uuid4()
    left_teacher_id = uuid4()
    other_teacher_id = uuid4()
    for tid in (co_teacher_id, left_teacher_id, other_teacher_id):
        identity["roles"][str(tid)] = ["TEACHER"]
    ClassTeacher.objects.create(
        class_section=section, user_id=co_teacher_id, role="CO_TEACHER", status="ACTIVE"
    )
    ClassTeacher.objects.create(
        class_section=section,
        user_id=left_teacher_id,
        role="CO_TEACHER",
        status="LEFT",
        left_at=datetime.now(UTC),
    )

    # Create 2nd open group in same class to test cross-group request_id tampering
    lead_b = uuid4()
    _enroll(section, lead_b)
    group_b = StudyGroup.objects.create(class_section=section, name="Nhóm B", is_recruiting=True)
    GroupMember.objects.create(
        class_section=section,
        group=group_b,
        enrollment=Enrollment.objects.get(class_section=section, user_id=lead_b),
        role="LEADER",
    )

    s1, s2, s3 = uuid4(), uuid4(), uuid4()
    for uid in (s1, s2, s3):
        _enroll(section, uid)

    # s1 requests group -> CO_TEACHER rejects (with idempotency replay & 422 payload mismatch)
    req_s1 = post_command(client_for(s1), f"/groups/{group.pk}/join-requests/", {}).json()["data"][
        "id"
    ]
    # Revoked (LEFT) and unassigned teachers get 404 on GET/approve/reject
    for bad_tid in (left_teacher_id, other_teacher_id):
        bad_c = client_for(bad_tid)
        _assert_vietnamese_error(bad_c.get(f"/groups/{group.pk}/join-requests/"), 404)
        _assert_vietnamese_error(
            post_command(bad_c, f"/groups/{group.pk}/join-requests/{req_s1}/approve/", {}), 404
        )
        _assert_vietnamese_error(
            post_command(bad_c, f"/groups/{group.pk}/join-requests/{req_s1}/reject/", {}), 404
        )

    # Cross-group request_id tampering: req_s1 belongs to `group`, NOT `group_b` -> 404
    _assert_vietnamese_error(
        post_command(
            client_for(lead_b), f"/groups/{group_b.pk}/join-requests/{req_s1}/approve/", {}
        ),
        404,
    )
    _assert_vietnamese_error(
        post_command(
            client_for(lead_b), f"/groups/{group_b.pk}/join-requests/{req_s1}/reject/", {}
        ),
        404,
    )
    _assert_vietnamese_error(
        post_command(client_for(s1), f"/groups/{group_b.pk}/join-requests/{req_s1}/cancel/", {}),
        404,
    )

    rej_key = uuid4()
    co_client = client_for(co_teacher_id)
    rej = post_command(
        co_client,
        f"/groups/{group.pk}/join-requests/{req_s1}/reject/",
        {"review_note": "Chưa phù hợp"},
        key=rej_key,
    )
    assert rej.status_code == 200 and rej.json()["data"]["status"] == "REJECTED"
    assert (
        post_command(
            co_client,
            f"/groups/{group.pk}/join-requests/{req_s1}/reject/",
            {"review_note": "Chưa phù hợp"},
            key=rej_key,
        ).status_code
        == 200
    )
    _assert_vietnamese_error(
        post_command(
            co_client,
            f"/groups/{group.pk}/join-requests/{req_s1}/reject/",
            {"review_note": "Khác nội dung"},
            key=rej_key,
        ),
        422,
        "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD",
    )

    # PRIMARY teacher approves s2 into group (with idempotency replay & 422)
    req_s2 = post_command(client_for(s2), f"/groups/{group.pk}/join-requests/", {}).json()["data"][
        "id"
    ]
    app_key = uuid4()
    teacher = client_for(actors["teacher"])
    app = post_command(
        teacher,
        f"/groups/{group.pk}/join-requests/{req_s2}/approve/",
        {"review_note": "GV duyệt"},
        key=app_key,
    )
    assert app.status_code == 200 and app.json()["data"]["status"] == "APPROVED"
    assert GroupMember.objects.filter(group=group, enrollment__user_id=s2, status="ACTIVE").exists()
    assert (
        post_command(
            teacher,
            f"/groups/{group.pk}/join-requests/{req_s2}/approve/",
            {"review_note": "GV duyệt"},
            key=app_key,
        ).status_code
        == 200
    )
    _assert_vietnamese_error(
        post_command(
            teacher,
            f"/groups/{group.pk}/join-requests/{req_s2}/approve/",
            {"review_note": "Ghi chú khác"},
            key=app_key,
        ),
        422,
        "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD",
    )

    # SYSTEM_ADMIN approves s3 into group_b
    req_s3 = post_command(client_for(s3), f"/groups/{group_b.pk}/join-requests/", {}).json()[
        "data"
    ]["id"]
    admin_app = post_command(
        client_for(actors["admin"]),
        f"/groups/{group_b.pk}/join-requests/{req_s3}/approve/",
        {"review_note": "Admin duyệt"},
    )
    assert admin_app.status_code == 200 and admin_app.json()["data"]["status"] == "APPROVED"
    assert GroupMember.objects.filter(
        group=group_b, enrollment__user_id=s3, status="ACTIVE"
    ).exists()

    # Cancel with empty body (no JSON payload) + unknown field rejection + idempotency replay
    req_cancel = post_command(client_for(s1), f"/groups/{group_b.pk}/join-requests/", {}).json()[
        "data"
    ]["id"]
    _assert_vietnamese_error(
        post_command(
            client_for(s1),
            f"/groups/{group_b.pk}/join-requests/{req_cancel}/cancel/",
            {"unexpected": True},
        ),
        400,
        "VALIDATION_ERROR",
    )
    cancel_key = str(uuid4())
    empty_cancel = client_for(s1).post(
        f"/groups/{group_b.pk}/join-requests/{req_cancel}/cancel/",
        HTTP_IDEMPOTENCY_KEY=cancel_key,
    )
    assert empty_cancel.status_code == 200 and empty_cancel.json()["data"]["status"] == "CANCELLED"
    replay_cancel = client_for(s1).post(
        f"/groups/{group_b.pk}/join-requests/{req_cancel}/cancel/",
        HTTP_IDEMPOTENCY_KEY=cancel_key,
    )
    assert replay_cancel.status_code == 200


def test_join_request_creation_and_approval_state_guards_and_vietnamese_messages(
    section, group, actors, client_for, post_command
):
    group.is_recruiting = True
    group.save(update_fields=["is_recruiting"])
    outsider = client_for(actors["outsider"])
    leader = client_for(actors["leader"])
    teacher = client_for(actors["teacher"])

    # message > 500 chars -> 400 Vietnamese
    _assert_vietnamese_error(
        post_command(outsider, f"/groups/{group.pk}/join-requests/", {"message": "a" * 501}),
        400,
        "VALIDATION_ERROR",
    )

    # Approve when enrollment became inactive (direct state race guard) -> 409 ENROLLMENT_INACTIVE
    s_inactive = uuid4()
    enr_inactive = _enroll(section, s_inactive)
    req_in = GroupJoinRequest.objects.create(
        class_section=section,
        group=group,
        enrollment=enr_inactive,
        user_id=s_inactive,
        status="PENDING",
    )
    enr_inactive.status = "LEFT"
    enr_inactive.left_at = datetime.now(UTC)
    enr_inactive.save(update_fields=["status", "left_at"])
    _assert_vietnamese_error(
        post_command(leader, f"/groups/{group.pk}/join-requests/{req_in.pk}/approve/", {}),
        409,
        "ENROLLMENT_INACTIVE",
    )

    # Approve when student already joined another group -> 409 ALREADY_IN_GROUP
    req_mem = GroupJoinRequest.objects.create(
        class_section=section,
        group=group,
        enrollment=Enrollment.objects.get(class_section=section, user_id=actors["member"]),
        user_id=actors["member"],
        status="PENDING",
    )
    _assert_vietnamese_error(
        post_command(leader, f"/groups/{group.pk}/join-requests/{req_mem.pk}/approve/", {}),
        409,
        "ALREADY_IN_GROUP",
    )

    # ARCHIVED group blocks POST /join-requests/
    archived_group = StudyGroup.objects.create(
        class_section=section, name="Nhóm Lưu Trữ", status="ARCHIVED", is_recruiting=True
    )
    _assert_vietnamese_error(
        post_command(outsider, f"/groups/{archived_group.pk}/join-requests/", {}),
        409,
        "GROUP_ARCHIVED",
    )

    # LOCKED class blocks POST /join-requests/ and approve
    post_command(teacher, f"/classes/{section.pk}/lock-grouping/", {"version": 1, "force": True})
    _assert_vietnamese_error(
        post_command(outsider, f"/groups/{group.pk}/join-requests/", {}),
        409,
        "GROUPING_LOCKED",
    )
    stale_pending = GroupJoinRequest.objects.create(
        class_section=section,
        group=group,
        enrollment=Enrollment.objects.get(class_section=section, user_id=actors["outsider"]),
        user_id=actors["outsider"],
        status="PENDING",
    )
    _assert_vietnamese_error(
        post_command(leader, f"/groups/{group.pk}/join-requests/{stale_pending.pk}/approve/", {}),
        409,
        "GROUPING_LOCKED",
    )

    # CLOSED class blocks POST /join-requests/, approve, reject, cancel
    post_command(teacher, f"/classes/{section.pk}/state/", {"version": 2, "status": "CLOSED"})
    _assert_vietnamese_error(
        post_command(outsider, f"/groups/{group.pk}/join-requests/", {}),
        409,
        "CLASS_NOT_OPEN",
    )
