from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from django.db import IntegrityError, connection, transaction

from apps.courses.models import ClassSection, ClassTeacher, Enrollment
from apps.groups.models import GroupJoinRequest, GroupMember, GroupTopicProposal, StudyGroup

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


def test_member_skills_and_responsibility_self_and_leader_updates(
    section, group, actors, client_for, post_command
):
    leader = client_for(actors["leader"])
    member = client_for(actors["member"])
    outsider = client_for(actors["outsider"])
    teacher = client_for(actors["teacher"])
    admin = client_for(actors["admin"])

    # Empty patch rejected
    assert member.patch(f"/groups/{group.pk}/members/me/", {}, format="json").status_code == 400
    # > 10 skills rejected
    assert (
        member.patch(
            f"/groups/{group.pk}/members/me/",
            {"skills": [f"K{i}" for i in range(11)]},
            format="json",
        ).status_code
        == 400
    )
    # Skill > 50 chars rejected
    assert (
        member.patch(
            f"/groups/{group.pk}/members/me/",
            {"skills": ["x" * 51]},
            format="json",
        ).status_code
        == 400
    )

    # Member updates own skills & responsibility
    self_patch = member.patch(
        f"/groups/{group.pk}/members/me/",
        {
            "skills": [" Python ", "Django", "python", "PostgreSQL"],
            "responsibility": "Backend API",
        },
        format="json",
    )
    assert self_patch.status_code == 200
    body = self_patch.json()["data"]
    assert body["skills"] == ["Python", "Django", "PostgreSQL"]
    assert body["responsibility"] == "Backend API"
    assert body["role"] == "MEMBER"

    # Partial update of responsibility preserves skills
    partial = member.patch(
        f"/groups/{group.pk}/members/me/",
        {"responsibility": "Backend & Database"},
        format="json",
    )
    assert partial.status_code == 200
    assert partial.json()["data"]["skills"] == ["Python", "Django", "PostgreSQL"]
    assert partial.json()["data"]["responsibility"] == "Backend & Database"

    # Non-member cannot call /members/me/
    assert (
        outsider.patch(
            f"/groups/{group.pk}/members/me/", {"responsibility": "Hack"}, format="json"
        ).status_code
        == 404
    )

    # Leader updates member's responsibility (preserves skills); Member/Teacher/Admin blocked (403)
    assert (
        member.patch(
            f"/groups/{group.pk}/members/{actors['leader']}/",
            {"responsibility": "Test"},
            format="json",
        ).status_code
        == 403
    )
    assert (
        teacher.patch(
            f"/groups/{group.pk}/members/{actors['member']}/",
            {"responsibility": "Test"},
            format="json",
        ).status_code
        == 403
    )
    assert (
        admin.patch(
            f"/groups/{group.pk}/members/{actors['member']}/",
            {"responsibility": "Test"},
            format="json",
        ).status_code
        == 404
    )  # admin not in group read unless admin_allowed=True on leader-only route
    assert (
        outsider.patch(
            f"/groups/{group.pk}/members/{actors['member']}/",
            {"responsibility": "Test"},
            format="json",
        ).status_code
        == 404
    )

    by_leader = leader.patch(
        f"/groups/{group.pk}/members/{actors['member']}/",
        {"responsibility": "Lead Backend Engineer"},
        format="json",
    )
    assert by_leader.status_code == 200
    assert by_leader.json()["data"]["responsibility"] == "Lead Backend Engineer"
    assert by_leader.json()["data"]["skills"] == ["Python", "Django", "PostgreSQL"]

    # Exposed in BOTH GET /groups/<id>/members/ and GET /classes/<id>/my-group/
    members_list = leader.get(f"/groups/{group.pk}/members/").json()["data"]
    member_row = next(row for row in members_list if row["user_id"] == str(actors["member"]))
    assert member_row["skills"] == ["Python", "Django", "PostgreSQL"]
    assert member_row["responsibility"] == "Lead Backend Engineer"

    my_group = member.get(f"/classes/{section.pk}/my-group/").json()["data"]
    my_row = next(row for row in my_group["members"] if row["user_id"] == str(actors["member"]))
    assert my_row["skills"] == ["Python", "Django", "PostgreSQL"]
    assert my_row["responsibility"] == "Lead Backend Engineer"

    # Recorded in group activities
    acts = leader.get(f"/groups/{group.pk}/activities/").json()["data"]
    verbs = {row["verb"] for row in acts}
    assert "group.member.profile.updated" in verbs
    assert "group.member.responsibility.updated" in verbs

    # Closed class blocks updates
    post_command(teacher, f"/classes/{section.pk}/state/", {"version": 1, "status": "CLOSED"})
    closed = member.patch(
        f"/groups/{group.pk}/members/me/", {"responsibility": "Late"}, format="json"
    )
    assert closed.status_code == 409 and closed.json()["error"]["code"] == "CLASS_NOT_OPEN"


def test_topic_proposal_full_lifecycle_permissions_versioning_and_activities(
    section, group, actors, client_for, identity, post_command
):
    leader = client_for(actors["leader"])
    member = client_for(actors["member"])
    outsider = client_for(actors["outsider"])
    teacher = client_for(actors["teacher"])
    admin = client_for(actors["admin"])

    # Assign a CO_TEACHER to verify CO_TEACHER can also review
    co_teacher_id = uuid4()
    identity["roles"][str(co_teacher_id)] = ["TEACHER"]
    ClassTeacher.objects.create(
        class_section=section, user_id=co_teacher_id, role="CO_TEACHER", status="ACTIVE"
    )
    co_teacher = client_for(co_teacher_id)

    # Before draft: GET returns 200 with data=None for members/teacher/admin; 404 for outsider
    for c in (leader, member, teacher, co_teacher, admin):
        empty = c.get(f"/groups/{group.pk}/topic/")
        assert empty.status_code == 200 and empty.json()["data"] is None
    assert outsider.get(f"/groups/{group.pk}/topic/").status_code == 404

    # Submit/review before draft exists -> 404
    assert (
        post_command(leader, f"/groups/{group.pk}/topic/submit/", {"version": 1}).status_code == 404
    )
    assert (
        post_command(
            teacher,
            f"/groups/{group.pk}/topic/review/",
            {"decision": "APPROVED", "version": 1},
        ).status_code
        == 404
    )

    # Non-leader member / Teacher cannot PUT topic
    payload = {
        "title": "Hệ thống quản lý học tập UTask",
        "summary": "Xây dựng nền tảng hỗ trợ sinh viên làm đồ án theo nhóm.",
        "objectives": "Hoàn thành quản lý công việc, nhóm và phản hồi giảng viên.",
    }
    assert member.put(f"/groups/{group.pk}/topic/", payload, format="json").status_code == 403
    assert teacher.put(f"/groups/{group.pk}/topic/", payload, format="json").status_code == 403
    assert outsider.put(f"/groups/{group.pk}/topic/", payload, format="json").status_code == 404

    # Leader creates initial draft -> 201, version=1, status=DRAFT
    created = leader.put(f"/groups/{group.pk}/topic/", payload, format="json")
    assert created.status_code == 201
    topic = created.json()["data"]
    assert topic["status"] == "DRAFT" and topic["version"] == 1

    # Updating existing draft requires version (400 if omitted, 409 if stale)
    assert leader.put(f"/groups/{group.pk}/topic/", payload, format="json").status_code == 400
    stale = leader.put(f"/groups/{group.pk}/topic/", {**payload, "version": 99}, format="json")
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "VERSION_CONFLICT"

    updated = leader.put(
        f"/groups/{group.pk}/topic/",
        {**payload, "title": "UTask — Hệ thống quản lý dự án học thuật", "version": 1},
        format="json",
    )
    assert updated.status_code == 200 and updated.json()["data"]["version"] == 2

    # Teacher cannot review DRAFT -> 409 TOPIC_NOT_PENDING
    not_pending = post_command(
        teacher,
        f"/groups/{group.pk}/topic/review/",
        {"decision": "APPROVED", "version": 2},
    )
    assert not_pending.status_code == 409
    assert not_pending.json()["error"]["code"] == "TOPIC_NOT_PENDING"

    # Leader submits DRAFT -> PENDING (version 3), idempotent replay works
    submit_key = uuid4()
    submitted = post_command(
        leader, f"/groups/{group.pk}/topic/submit/", {"version": 2}, key=submit_key
    )
    assert submitted.status_code == 200
    assert submitted.json()["data"]["status"] == "PENDING"
    assert submitted.json()["data"]["version"] == 3
    assert submitted.json()["data"]["submitted_by_user_id"] == str(actors["leader"])
    assert submitted.json()["data"]["submitted_at"] is not None
    replayed = post_command(
        leader, f"/groups/{group.pk}/topic/submit/", {"version": 2}, key=submit_key
    )
    assert replayed.status_code == 200 and replayed.json()["data"]["version"] == 3

    # Cannot edit while PENDING -> 409 TOPIC_NOT_EDITABLE
    locked_edit = leader.put(f"/groups/{group.pk}/topic/", {**payload, "version": 3}, format="json")
    assert locked_edit.status_code == 409
    assert locked_edit.json()["error"]["code"] == "TOPIC_NOT_EDITABLE"

    # Admin (without active teacher assignment), Leader, Member cannot review -> 403
    for non_teacher in (admin, leader, member):
        denied = post_command(
            non_teacher,
            f"/groups/{group.pk}/topic/review/",
            {"decision": "APPROVED", "version": 3},
        )
        assert denied.status_code == 403

    # REVISION_REQUESTED & REJECTED require non-empty feedback (400)
    missing_fb = post_command(
        teacher,
        f"/groups/{group.pk}/topic/review/",
        {"decision": "REVISION_REQUESTED", "feedback": "   ", "version": 3},
    )
    assert missing_fb.status_code == 400

    # CO_TEACHER requests revision -> version 4, REVISION_REQUESTED
    rev = post_command(
        co_teacher,
        f"/groups/{group.pk}/topic/review/",
        {
            "decision": "REVISION_REQUESTED",
            "feedback": "Cần làm rõ phạm vi kiểm thử và kiến trúc dữ liệu.",
            "version": 3,
        },
    )
    assert rev.status_code == 200
    assert rev.json()["data"]["status"] == "REVISION_REQUESTED"
    assert rev.json()["data"]["version"] == 4
    assert rev.json()["data"]["reviewed_by_user_id"] == str(co_teacher_id)

    # Cannot directly re-submit REVISION_REQUESTED without editing via PUT first
    cant_resubmit = post_command(leader, f"/groups/{group.pk}/topic/submit/", {"version": 4})
    assert cant_resubmit.status_code == 409
    assert cant_resubmit.json()["error"]["code"] == "TOPIC_NOT_SUBMITTABLE"

    # Leader edits after REVISION_REQUESTED -> status resets to DRAFT, version 5
    revised = leader.put(
        f"/groups/{group.pk}/topic/",
        {**payload, "objectives": "Bổ sung kế hoạch kiểm thử tích hợp.", "version": 4},
        format="json",
    )
    assert revised.status_code == 200
    assert revised.json()["data"]["status"] == "DRAFT"
    assert revised.json()["data"]["version"] == 5

    # Resubmit (v6) -> Reject (v7) -> Edit (v8) -> Resubmit (v9) -> Approve (v10)
    assert (
        post_command(leader, f"/groups/{group.pk}/topic/submit/", {"version": 5}).status_code == 200
    )
    rej = post_command(
        teacher,
        f"/groups/{group.pk}/topic/review/",
        {"decision": "REJECTED", "feedback": "Đề tài trùng nhóm khác.", "version": 6},
    )
    assert rej.status_code == 200 and rej.json()["data"]["status"] == "REJECTED"

    redraft = leader.put(
        f"/groups/{group.pk}/topic/",
        {
            "title": "Hệ thống theo dõi tiến độ đồ án theo sprint",
            "summary": "Đề tài mới hoàn toàn độc lập.",
            "objectives": "Hoàn thành bảng Kanban và báo cáo tiến độ.",
            "version": 7,
        },
        format="json",
    )
    assert redraft.status_code == 200 and redraft.json()["data"]["version"] == 8
    assert (
        post_command(leader, f"/groups/{group.pk}/topic/submit/", {"version": 8}).status_code == 200
    )
    approved = post_command(
        teacher,
        f"/groups/{group.pk}/topic/review/",
        {"decision": "APPROVED", "feedback": "Đề tài đạt yêu cầu.", "version": 9},
    )
    assert approved.status_code == 200
    assert approved.json()["data"]["status"] == "APPROVED"
    assert approved.json()["data"]["version"] == 10

    # Once APPROVED, cannot edit or resubmit
    assert (
        leader.put(f"/groups/{group.pk}/topic/", {**payload, "version": 10}, format="json").json()[
            "error"
        ]["code"]
        == "TOPIC_NOT_EDITABLE"
    )

    # Full review history preserved in GET /groups/<id>/activities/
    activities = teacher.get(f"/groups/{group.pk}/activities/").json()["data"]
    topic_verbs = [row["verb"] for row in activities if row["subject_type"] == "GroupTopicProposal"]
    assert "group.topic.created" in topic_verbs
    assert topic_verbs.count("group.topic.updated") == 3
    assert topic_verbs.count("group.topic.submitted") == 3
    assert topic_verbs.count("group.topic.reviewed") == 3


def test_topic_proposal_postgres_one_to_one_and_same_class_fk(section, group):
    GroupTopicProposal.objects.create(
        class_section=section,
        group=group,
        title="Đề tài 1",
        summary="Mô tả 1",
    )
    # 1-1 unique constraint blocks second proposal for same group
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            GroupTopicProposal.objects.create(
                class_section=section,
                group=group,
                title="Đề tài 2",
                summary="Mô tả 2",
            )

    # Same-class composite FK blocks mismatched (class_section, group)
    other_section = ClassSection.objects.create(
        course=section.course,
        code="SE99",
        name="Lớp Khác",
        term="2026",
        starts_on=date(2026, 1, 1),
        ends_on=date(2026, 12, 31),
    )
    other_group = StudyGroup.objects.create(class_section=other_section, name="Nhóm Khác Lớp")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            GroupTopicProposal.objects.create(
                class_section=section,
                group=other_group,
                title="Đề tài lệch lớp",
                summary="Không hợp lệ",
            )
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_member_skills_and_responsibility_edge_cases_security_and_locked_class(
    section, group, actors, client_for, post_command
):
    leader = client_for(actors["leader"])
    member = client_for(actors["member"])
    teacher = client_for(actors["teacher"])

    # Cannot escalate role via extra field on /members/me/
    _assert_vietnamese_error(
        member.patch(
            f"/groups/{group.pk}/members/me/",
            {"role": "LEADER", "responsibility": "Tự phong"},
            format="json",
        ),
        400,
        "VALIDATION_ERROR",
    )
    # Non-list skills & responsibility > 200 chars -> 400 Vietnamese
    _assert_vietnamese_error(
        member.patch(f"/groups/{group.pk}/members/me/", {"skills": "Python"}, format="json"),
        400,
        "VALIDATION_ERROR",
    )
    _assert_vietnamese_error(
        member.patch(
            f"/groups/{group.pk}/members/me/", {"responsibility": "r" * 201}, format="json"
        ),
        400,
        "VALIDATION_ERROR",
    )

    # Clear skills to [] and responsibility to ""
    cleared = member.patch(
        f"/groups/{group.pk}/members/me/",
        {"skills": [], "responsibility": ""},
        format="json",
    )
    assert cleared.status_code == 200
    assert cleared.json()["data"]["skills"] == []
    assert cleared.json()["data"]["responsibility"] == ""

    # Leader updates OWN responsibility via /members/{leader_id}/
    self_leader = leader.patch(
        f"/groups/{group.pk}/members/{actors['leader']}/",
        {"responsibility": "PM & Kiến trúc hệ thống"},
        format="json",
    )
    assert self_leader.status_code == 200
    assert self_leader.json()["data"]["responsibility"] == "PM & Kiến trúc hệ thống"

    # Still works AFTER class lock-grouping
    assert (
        post_command(
            teacher, f"/classes/{section.pk}/lock-grouping/", {"version": 1, "force": True}
        ).status_code
        == 200
    )
    after_lock = member.patch(
        f"/groups/{group.pk}/members/me/",
        {"skills": ["QA"], "responsibility": "Kiểm thử tích hợp"},
        format="json",
    )
    assert after_lock.status_code == 200

    # Target inactive (REMOVED) member returns 404
    now = datetime.now(UTC)
    removed_uid = uuid4()
    rem_enr = Enrollment.objects.create(class_section=section, user_id=removed_uid)
    GroupMember.objects.create(
        class_section=section,
        group=group,
        enrollment=rem_enr,
        role="MEMBER",
        status="REMOVED",
        joined_at=now,
        left_at=now,
    )
    _assert_vietnamese_error(
        leader.patch(
            f"/groups/{group.pk}/members/{removed_uid}/",
            {"responsibility": "Cũ"},
            format="json",
        ),
        404,
        "RESOURCE_NOT_FOUND",
    )

    # ARCHIVED group rejects member profile & responsibility updates
    group.status = "ARCHIVED"
    group.save(update_fields=["status"])
    _assert_vietnamese_error(
        member.patch(f"/groups/{group.pk}/members/me/", {"responsibility": "Muộn"}, format="json"),
        409,
        "GROUP_ARCHIVED",
    )
    _assert_vietnamese_error(
        leader.patch(
            f"/groups/{group.pk}/members/{actors['member']}/",
            {"responsibility": "Muộn"},
            format="json",
        ),
        409,
        "GROUP_ARCHIVED",
    )


def test_topic_proposal_edge_cases_revoked_teacher_state_guards_and_group_activity_isolation(
    section, group, actors, client_for, post_command, identity
):
    leader = client_for(actors["leader"])
    teacher = client_for(actors["teacher"])

    # Revoked (LEFT) teacher -> 404 on GET and review
    revoked_tid = uuid4()
    identity["roles"][str(revoked_tid)] = ["TEACHER"]
    ClassTeacher.objects.create(
        class_section=section,
        user_id=revoked_tid,
        role="CO_TEACHER",
        status="LEFT",
        left_at=datetime.now(UTC),
    )
    revoked = client_for(revoked_tid)
    _assert_vietnamese_error(revoked.get(f"/groups/{group.pk}/topic/"), 404, "RESOURCE_NOT_FOUND")

    # Initial PUT validation edge cases
    _assert_vietnamese_error(
        leader.put(
            f"/groups/{group.pk}/topic/",
            {"title": "   ", "summary": "Hợp lệ"},
            format="json",
        ),
        400,
        "VALIDATION_ERROR",
    )
    _assert_vietnamese_error(
        leader.put(
            f"/groups/{group.pk}/topic/",
            {"title": "Hợp lệ", "summary": "x" * 5001},
            format="json",
        ),
        400,
        "VALIDATION_ERROR",
    )
    _assert_vietnamese_error(
        leader.put(
            f"/groups/{group.pk}/topic/",
            {"title": "Hợp lệ", "summary": "Hợp lệ", "objectives": "o" * 5001},
            format="json",
        ),
        400,
        "VALIDATION_ERROR",
    )
    _assert_vietnamese_error(
        leader.put(
            f"/groups/{group.pk}/topic/",
            {"title": "Hợp lệ", "summary": "Hợp lệ", "version": 2},
            format="json",
        ),
        409,
        "VERSION_CONFLICT",
    )

    # Create -> Submit -> Review edge cases (stale version, revoked teacher, replay & 422)
    created = leader.put(
        f"/groups/{group.pk}/topic/",
        {"title": "Đề tài A", "summary": "Mô tả đề tài A"},
        format="json",
    )
    assert created.status_code == 201
    assert (
        post_command(leader, f"/groups/{group.pk}/topic/submit/", {"version": 1}).status_code == 200
    )

    _assert_vietnamese_error(
        post_command(
            revoked,
            f"/groups/{group.pk}/topic/review/",
            {"decision": "APPROVED", "version": 2},
        ),
        404,
        "RESOURCE_NOT_FOUND",
    )
    _assert_vietnamese_error(
        post_command(
            teacher,
            f"/groups/{group.pk}/topic/review/",
            {"decision": "APPROVED", "version": 99},
        ),
        409,
        "VERSION_CONFLICT",
    )

    # APPROVED without feedback succeeds, replays idempotently, and blocks mismatched payload
    rev_key = uuid4()
    approved = post_command(
        teacher,
        f"/groups/{group.pk}/topic/review/",
        {"decision": "APPROVED", "version": 2},
        key=rev_key,
    )
    assert approved.status_code == 200
    assert approved.json()["data"]["status"] == "APPROVED"
    assert approved.json()["data"]["teacher_feedback"] == ""
    assert approved.json()["data"]["version"] == 3

    replayed = post_command(
        teacher,
        f"/groups/{group.pk}/topic/review/",
        {"decision": "APPROVED", "version": 2},
        key=rev_key,
    )
    assert replayed.status_code == 200 and replayed.json()["data"]["version"] == 3

    _assert_vietnamese_error(
        post_command(
            teacher,
            f"/groups/{group.pk}/topic/review/",
            {"decision": "REJECTED", "feedback": "Đổi ý", "version": 2},
            key=rev_key,
        ),
        422,
        "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD",
    )

    # Cross-group activity isolation: group_b in SAME class creates topic/request/member logs
    lead_b_uid = uuid4()
    enr_b = Enrollment.objects.create(class_section=section, user_id=lead_b_uid)
    group_b = StudyGroup.objects.create(class_section=section, name="Nhóm B", is_recruiting=True)
    GroupMember.objects.create(
        class_section=section, group=group_b, enrollment=enr_b, role="LEADER"
    )
    lead_b = client_for(lead_b_uid)
    assert (
        lead_b.patch(
            f"/groups/{group_b.pk}/members/me/", {"skills": ["Go"]}, format="json"
        ).status_code
        == 200
    )
    assert (
        lead_b.put(
            f"/groups/{group_b.pk}/topic/",
            {"title": "Đề tài B mật", "summary": "Không được rò rỉ sang nhóm A"},
            format="json",
        ).status_code
        == 201
    )
    req_b = post_command(
        client_for(actors["outsider"]), f"/groups/{group_b.pk}/join-requests/", {"message": "Vào B"}
    )
    assert req_b.status_code == 201

    group_a_acts = leader.get(f"/groups/{group.pk}/activities/").json()["data"]
    b_ids = {
        str(group_b.pk),
        str(GroupTopicProposal.objects.get(group=group_b).pk),
        str(GroupJoinRequest.objects.get(group=group_b).pk),
        str(GroupMember.objects.get(group=group_b, status="ACTIVE").pk),
    }
    assert all(row["subject_id"] not in b_ids for row in group_a_acts)

    # CLOSED class blocks PUT / submit / review on group_b
    post_command(teacher, f"/classes/{section.pk}/state/", {"version": 1, "status": "CLOSED"})
    _assert_vietnamese_error(
        lead_b.put(
            f"/groups/{group_b.pk}/topic/",
            {"title": "Sửa muộn", "summary": "Lớp đã đóng", "version": 1},
            format="json",
        ),
        409,
        "CLASS_NOT_OPEN",
    )
    _assert_vietnamese_error(
        post_command(lead_b, f"/groups/{group_b.pk}/topic/submit/", {"version": 1}),
        409,
        "CLASS_NOT_OPEN",
    )
    _assert_vietnamese_error(
        post_command(
            teacher,
            f"/groups/{group_b.pk}/topic/review/",
            {"decision": "APPROVED", "version": 1},
        ),
        409,
        "CLASS_NOT_OPEN",
    )

    # Reopen class, archive group_b -> ARCHIVED group blocks PUT / submit / review
    post_command(teacher, f"/classes/{section.pk}/state/", {"version": 2, "status": "OPEN"})
    group_b.status = "ARCHIVED"
    group_b.save(update_fields=["status"])
    _assert_vietnamese_error(
        lead_b.put(
            f"/groups/{group_b.pk}/topic/",
            {"title": "Sửa sau lưu trữ", "summary": "Nhóm đã lưu trữ", "version": 1},
            format="json",
        ),
        409,
        "GROUP_ARCHIVED",
    )
    _assert_vietnamese_error(
        post_command(lead_b, f"/groups/{group_b.pk}/topic/submit/", {"version": 1}),
        409,
        "GROUP_ARCHIVED",
    )
    _assert_vietnamese_error(
        post_command(
            teacher,
            f"/groups/{group_b.pk}/topic/review/",
            {"decision": "APPROVED", "version": 1},
        ),
        409,
        "GROUP_ARCHIVED",
    )
