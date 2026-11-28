"""End-to-end integration tests for Classroom flows and PostgreSQL constraints."""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from uuid import uuid4

import pytest
from allauth.account.models import EmailAddress
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from apps.accounts.models import (
    AccountStatus,
    GlobalRole,
    GlobalRoleCode,
    User,
    UserGlobalRole,
    UserSession,
)
from apps.accounts.roles import ROLE_SEEDS
from apps.activities.models import ClassroomActivity
from apps.authentication.adapters.session_tokens import FamilyRefreshToken, token_expiry
from apps.courses.models import ClassSection, Course, Enrollment
from apps.groups.models import GroupMember, StudyGroup
from apps.messaging.models import OutboxEvent, OutboxProducer

pytestmark = pytest.mark.integration


def _ensure_roles() -> dict[str, GlobalRole]:
    roles: dict[str, GlobalRole] = {}
    for code, name, description in ROLE_SEEDS:
        role, _ = GlobalRole.objects.get_or_create(
            code=code,
            defaults={"name": name, "description": description},
        )
        roles[code] = role
    return roles


def _create_user(
    *,
    roles: tuple[str, ...] = (GlobalRoleCode.STUDENT,),
    email: str | None = None,
    first_name: str = "An",
    last_name: str = "Nguyen",
    student_id: str | None = None,
    status: str = AccountStatus.ACTIVE,
) -> User:
    role_map = _ensure_roles()
    suffix = uuid4().hex[:8]
    primary_role = roles[0]
    user = User.objects.create_user(
        email=email or f"cls_{suffix}@example.edu.vn",
        username=f"cls_{suffix}",
        password="StrongPass123!",
        student_id=student_id,
        first_name=first_name,
        last_name=last_name,
        global_role_code=primary_role,
        account_status=status,
    )
    for extra_role in roles[1:]:
        UserGlobalRole.objects.get_or_create(user=user, role=role_map[extra_role])
    EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
    return user


def _client_for(user: User) -> APIClient:
    refresh = FamilyRefreshToken.for_user(user)
    session_id = uuid4()
    family = uuid4()
    refresh["session_id"] = str(session_id)
    refresh["token_family"] = str(family)
    refresh["family_exp"] = refresh["exp"]
    raw_refresh = str(refresh)
    UserSession.objects.create(
        id=session_id,
        user=user,
        token_family=family,
        refresh_token_hash=hashlib.sha256(raw_refresh.encode()).hexdigest(),
        refresh_jti=refresh["jti"],
        ip_address="127.0.0.1",
        user_agent="pytest-classroom",
        expires_at=token_expiry(refresh),
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client


def _idem() -> dict[str, str]:
    return {"HTTP_IDEMPOTENCY_KEY": str(uuid4())}


def _create_course_api(client: APIClient, *, code: str | None = None, name: str = "CNPM") -> dict:
    course_code = code or f"SE{uuid4().hex[:6].upper()}"
    resp = client.post(
        "/api/classroom/courses/",
        {"code": course_code, "name": name},
        format="json",
        **_idem(),
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()["data"]


def _create_class_api(
    client: APIClient,
    course_id: str,
    *,
    code: str | None = None,
    name: str = "Lớp SE101-01",
    group_min_size: int = 2,
    group_max_size: int = 4,
) -> dict:
    class_code = code or f"CLS{uuid4().hex[:6].upper()}"
    today = date.today()
    resp = client.post(
        "/api/classroom/classes/",
        {
            "course_id": course_id,
            "code": class_code,
            "name": name,
            "term": "2026-1",
            "starts_on": today.isoformat(),
            "ends_on": (today + timedelta(days=90)).isoformat(),
            "group_min_size": group_min_size,
            "group_max_size": group_max_size,
        },
        format="json",
        **_idem(),
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()["data"]


def _issue_class_join_code(client: APIClient, class_id: str, version: int) -> tuple[str, int]:
    resp = client.post(
        f"/api/classroom/classes/{class_id}/join-code/",
        {"version": version, "enabled": True},
        format="json",
        **_idem(),
    )
    assert resp.status_code == 200, resp.json()
    data = resp.json()["data"]
    return data["code"], data["version"]


def _join_class_via_code(client: APIClient, code: str) -> dict:
    resp = client.post(
        "/api/classroom/classes/join/",
        {"code": code},
        format="json",
        **_idem(),
    )
    assert resp.status_code == 201, resp.json()
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# 1. Courses CRUD, archive/unarchive, duplicate 409, student 403
# ---------------------------------------------------------------------------


def test_courses_crud_archive_duplicate_and_permissions(db):
    teacher = _create_user(roles=(GlobalRoleCode.TEACHER,))
    other_teacher = _create_user(roles=(GlobalRoleCode.TEACHER,))
    admin = _create_user(roles=(GlobalRoleCode.SYSTEM_ADMIN,))
    student = _create_user(roles=(GlobalRoleCode.STUDENT,))

    t_client = _client_for(teacher)
    other_t_client = _client_for(other_teacher)
    admin_client = _client_for(admin)
    s_client = _client_for(student)

    # Student cannot create a course -> 403.
    forbidden = s_client.post(
        "/api/classroom/courses/",
        {"code": "CS101", "name": "Intro"},
        format="json",
        **_idem(),
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "PERMISSION_DENIED"

    # Teacher creates a course (code normalized uppercase) + idempotency replay.
    idem_headers = _idem()
    create_payload = {"code": "  se301 ", "name": "Kiến trúc phần mềm"}
    created = t_client.post(
        "/api/classroom/courses/",
        create_payload,
        format="json",
        **idem_headers,
    )
    assert created.status_code == 201
    course = created.json()["data"]
    assert course["code"] == "SE301"
    assert course["archived_at"] is None
    course_id = course["id"]

    replayed = t_client.post(
        "/api/classroom/courses/",
        create_payload,
        format="json",
        **idem_headers,
    )
    assert replayed.status_code == 201
    assert replayed.json()["data"]["id"] == course_id

    # Duplicate code with a new idempotency key -> 409 COURSE_CODE_EXISTS.
    dup = t_client.post(
        "/api/classroom/courses/",
        {"code": "SE301", "name": "Duplicate"},
        format="json",
        **_idem(),
    )
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "COURSE_CODE_EXISTS"

    # List & detail.
    listed = t_client.get("/api/classroom/courses/", {"search": "SE301"})
    assert listed.status_code == 200
    assert [c["id"] for c in listed.json()["data"]] == [course_id]

    detail = t_client.get(f"/api/classroom/courses/{course_id}/")
    assert detail.status_code == 200
    assert detail.json()["data"]["name"] == "Kiến trúc phần mềm"

    # Unenrolled student does not see the course.
    assert s_client.get("/api/classroom/courses/").json()["data"] == []
    assert s_client.get(f"/api/classroom/courses/{course_id}/").status_code == 404

    # Other teacher cannot update someone else's course -> 403.
    other_patch = other_t_client.patch(
        f"/api/classroom/courses/{course_id}/",
        {"name": "Hijack"},
        format="json",
        **_idem(),
    )
    assert other_patch.status_code == 403

    # Owner updates, archives, and admin unarchives.
    updated = t_client.patch(
        f"/api/classroom/courses/{course_id}/",
        {"name": "Kiến trúc phần mềm nâng cao"},
        format="json",
        **_idem(),
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["name"] == "Kiến trúc phần mềm nâng cao"

    archived = t_client.post(
        f"/api/classroom/courses/{course_id}/archive/",
        {},
        format="json",
        **_idem(),
    )
    assert archived.status_code == 200
    assert archived.json()["data"]["archived_at"] is not None

    only_archived = t_client.get("/api/classroom/courses/", {"archived": "true"})
    assert [c["id"] for c in only_archived.json()["data"]] == [course_id]

    unarchived = admin_client.post(
        f"/api/classroom/courses/{course_id}/unarchive/",
        {},
        format="json",
        **_idem(),
    )
    assert unarchived.status_code == 200
    assert unarchived.json()["data"]["archived_at"] is None


# ---------------------------------------------------------------------------
# 2. Class sections: CRUD, state transitions, lock/unlock, join-code, summary, teachers
# ---------------------------------------------------------------------------


def test_class_sections_lifecycle_summary_and_teachers(db):
    teacher = _create_user(roles=(GlobalRoleCode.TEACHER,))
    co_teacher = _create_user(roles=(GlobalRoleCode.TEACHER,))
    student = _create_user(roles=(GlobalRoleCode.STUDENT,))

    t_client = _client_for(teacher)
    s_client = _client_for(student)

    course = _create_course_api(t_client)
    section = _create_class_api(t_client, course["id"], group_min_size=2, group_max_size=4)
    class_id = section["id"]
    version = section["version"]
    assert section["status"] == "OPEN"
    assert section["grouping_phase"] == "FORMING"
    assert section["primary_teacher_id"] == str(teacher.pk)

    # List & detail.
    listed = t_client.get("/api/classroom/classes/", {"course_id": course["id"]})
    assert listed.status_code == 200
    assert any(item["id"] == class_id for item in listed.json()["data"])

    detail = t_client.get(f"/api/classroom/classes/{class_id}/")
    assert detail.status_code == 200
    assert detail.json()["data"]["id"] == class_id

    # Update class & check stale version conflict.
    stale_patch = t_client.patch(
        f"/api/classroom/classes/{class_id}/",
        {"version": 999, "name": "Stale"},
        format="json",
        **_idem(),
    )
    assert stale_patch.status_code == 409
    assert stale_patch.json()["error"]["code"] == "VERSION_CONFLICT"

    patched = t_client.patch(
        f"/api/classroom/classes/{class_id}/",
        {"version": version, "name": "Lớp SE101 Cập nhật"},
        format="json",
        **_idem(),
    )
    assert patched.status_code == 200
    version = patched.json()["data"]["version"]
    assert patched.json()["data"]["name"] == "Lớp SE101 Cập nhật"

    # Assign co-teacher & list teachers; reject non-teacher user.
    bad_teacher = t_client.post(
        f"/api/classroom/classes/{class_id}/teachers/assign/",
        {"version": version, "user_id": str(student.pk), "role": "CO_TEACHER", "status": "ACTIVE"},
        format="json",
        **_idem(),
    )
    assert bad_teacher.status_code == 422
    assert bad_teacher.json()["error"]["code"] == "INVALID_TEACHER"

    assign_resp = t_client.post(
        f"/api/classroom/classes/{class_id}/teachers/assign/",
        {
            "version": version,
            "user_id": str(co_teacher.pk),
            "role": "CO_TEACHER",
            "status": "ACTIVE",
        },
        format="json",
        **_idem(),
    )
    assert assign_resp.status_code == 200
    version = assign_resp.json()["data"]["version"]

    teachers_list = t_client.get(f"/api/classroom/classes/{class_id}/teachers/")
    assert teachers_list.status_code == 200
    teacher_ids = {item["user_id"] for item in teachers_list.json()["data"]}
    assert teacher_ids == {str(teacher.pk), str(co_teacher.pk)}

    # Remove co-teacher -> OK; then removing last teacher -> 409 LAST_TEACHER_REQUIRED.
    remove_co = t_client.post(
        f"/api/classroom/classes/{class_id}/teachers/assign/",
        {
            "version": version,
            "user_id": str(co_teacher.pk),
            "role": "CO_TEACHER",
            "status": "LEFT",
        },
        format="json",
        **_idem(),
    )
    assert remove_co.status_code == 200
    version = remove_co.json()["data"]["version"]

    remove_last = t_client.post(
        f"/api/classroom/classes/{class_id}/teachers/assign/",
        {"version": version, "user_id": str(teacher.pk), "role": "PRIMARY", "status": "LEFT"},
        format="json",
        **_idem(),
    )
    assert remove_last.status_code == 409
    assert remove_last.json()["error"]["code"] == "LAST_TEACHER_REQUIRED"

    # Join-code issue & rotate; old code stops working, new code works.
    code1, version = _issue_class_join_code(t_client, class_id, version)
    code2, version = _issue_class_join_code(t_client, class_id, version)
    assert code1 != code2
    old_join = s_client.post(
        "/api/classroom/classes/join/",
        {"code": code1},
        format="json",
        **_idem(),
    )
    assert old_join.status_code == 404
    _join_class_via_code(s_client, code2)

    # Summary endpoints: student is unassigned -> students_without_team_count == 1.
    summary = t_client.get(f"/api/classroom/classes/{class_id}/summary/")
    assert summary.status_code == 200
    s_data = summary.json()["data"]
    assert s_data["enrolled_active_count"] == 1
    assert s_data["active_group_count"] == 0
    assert s_data["students_without_team_count"] == 1

    teacher_summaries = t_client.get("/api/classroom/teacher/classes/summary/", {"status": "OPEN"})
    assert teacher_summaries.status_code == 200
    assert any(item["class_id"] == class_id for item in teacher_summaries.json()["data"])
    assert s_client.get("/api/classroom/teacher/classes/summary/").status_code == 403

    # Lock grouping without force fails due to unassigned student -> 409; force=True succeeds.
    lock_blocked = t_client.post(
        f"/api/classroom/classes/{class_id}/lock-grouping/",
        {"version": version},
        format="json",
        **_idem(),
    )
    assert lock_blocked.status_code == 409
    assert lock_blocked.json()["error"]["code"] == "GROUPING_PRECONDITIONS_UNMET"

    locked = t_client.post(
        f"/api/classroom/classes/{class_id}/lock-grouping/",
        {"version": version, "force": True},
        format="json",
        **_idem(),
    )
    assert locked.status_code == 200
    assert locked.json()["data"]["grouping_phase"] == "LOCKED"
    assert locked.json()["data"]["grouping_locked_at"] is not None
    version = locked.json()["data"]["version"]

    unlocked = t_client.post(
        f"/api/classroom/classes/{class_id}/unlock-grouping/",
        {"version": version, "reason": "Mở thêm để sinh viên ghép nhóm"},
        format="json",
        **_idem(),
    )
    assert unlocked.status_code == 200
    assert unlocked.json()["data"]["grouping_phase"] == "FORMING"
    assert unlocked.json()["data"]["grouping_locked_at"] is None
    version = unlocked.json()["data"]["version"]

    # State transitions: OPEN -> CLOSED -> ARCHIVED, and ARCHIVED cannot reopen.
    closed = t_client.post(
        f"/api/classroom/classes/{class_id}/state/",
        {"version": version, "status": "CLOSED"},
        format="json",
        **_idem(),
    )
    assert closed.status_code == 200
    assert closed.json()["data"]["status"] == "CLOSED"
    version = closed.json()["data"]["version"]

    archived = t_client.post(
        f"/api/classroom/classes/{class_id}/state/",
        {"version": version, "status": "ARCHIVED"},
        format="json",
        **_idem(),
    )
    assert archived.status_code == 200
    assert archived.json()["data"]["status"] == "ARCHIVED"
    version = archived.json()["data"]["version"]

    reopen = t_client.post(
        f"/api/classroom/classes/{class_id}/state/",
        {"version": version, "status": "OPEN"},
        format="json",
        **_idem(),
    )
    assert reopen.status_code == 409
    assert reopen.json()["error"]["code"] == "CLASS_ARCHIVED"


# ---------------------------------------------------------------------------
# 3. Enrollments (join, list, exit, reactivate) & Student Import in-process
# ---------------------------------------------------------------------------


def test_enrollments_lifecycle_and_student_import_provisioning(db, settings):
    settings.IDENTITY_REQUIRE_EMAIL_ACTIVATION = True

    teacher = _create_user(roles=(GlobalRoleCode.TEACHER,))
    existing_student = _create_user(
        roles=(GlobalRoleCode.STUDENT,),
        email="existing.sv@example.edu.vn",
        student_id="SV2026001",
    )
    join_student = _create_user(
        roles=(GlobalRoleCode.STUDENT,),
        email="joiner.sv@example.edu.vn",
        student_id="SV2026002",
    )

    t_client = _client_for(teacher)
    s_client = _client_for(join_student)

    course = _create_course_api(t_client)
    section = _create_class_api(t_client, course["id"])
    class_id = section["id"]
    join_code, _ver = _issue_class_join_code(t_client, class_id, section["version"])

    # Student joins by join-code, exits, cannot rejoin via code, teacher reactivates.
    enrollment = _join_class_via_code(s_client, join_code)
    enrollment_id = enrollment["id"]
    assert enrollment["status"] == "ACTIVE"
    assert enrollment["source"] == "SELF"

    list_resp = t_client.get(f"/api/classroom/classes/{class_id}/enrollments/")
    assert list_resp.status_code == 200
    assert len(list_resp.json()["data"]) == 1
    assert list_resp.json()["data"][0]["profile"]["student_id"] == "SV2026002"

    exit_resp = s_client.post(
        f"/api/classroom/classes/{class_id}/enrollments/{enrollment_id}/exit/",
        {"reason": "Rút học phần"},
        format="json",
        **_idem(),
    )
    assert exit_resp.status_code == 200
    assert exit_resp.json()["data"]["status"] == "LEFT"

    rejoin_blocked = s_client.post(
        "/api/classroom/classes/join/",
        {"code": join_code},
        format="json",
        **_idem(),
    )
    assert rejoin_blocked.status_code == 409
    assert rejoin_blocked.json()["error"]["code"] == "ENROLLMENT_INACTIVE"

    reactivated = t_client.post(
        f"/api/classroom/classes/{class_id}/enrollments/{enrollment_id}/reactivate/",
        {"reason": "Sinh viên quay lại lớp"},
        format="json",
        **_idem(),
    )
    assert reactivated.status_code == 200
    assert reactivated.json()["data"]["status"] == "ACTIVE"
    assert reactivated.json()["data"]["left_at"] is None

    # Student list import calling apps.accounts.interface.provision_students in-process.
    new_email = f"imported_{uuid4().hex[:6]}@example.edu.vn"
    new_mssv = f"SV{uuid4().hex[:6].upper()}"
    import_resp = t_client.post(
        f"/api/classroom/classes/{class_id}/students/",
        {
            "students": [
                {
                    "row_number": 1,
                    "email": new_email,
                    "student_id": new_mssv,
                    "first_name": "Lan",
                    "last_name": "Le",
                },
                {
                    "row_number": 2,
                    "email": existing_student.email,
                    "student_id": existing_student.student_id,
                    "first_name": "Existing",
                    "last_name": "User",
                },
                {
                    "row_number": 3,
                    "email": new_email,
                    "student_id": new_mssv,
                    "first_name": "Dup",
                    "last_name": "Row",
                },
                {
                    "row_number": 4,
                    "email": teacher.email,
                    "first_name": "Teacher",
                    "last_name": "Conflict",
                },
            ]
        },
        format="json",
        **_idem(),
    )
    assert import_resp.status_code == 200, import_resp.json()
    import_data = import_resp.json()["data"]
    summary = import_data["summary"]
    assert summary["total_records"] == 4
    assert summary["created_accounts"] == 1
    assert summary["existing_accounts"] == 1
    assert summary["enrolled"] == 2
    assert summary["duplicates"] == 1
    assert summary["flagged"] == 1

    # Verify real User + Enrollment + identity.student.imported outbox row created atomically.
    created_user = User.objects.get(email=new_email)
    assert created_user.student_id == new_mssv
    assert created_user.account_status == AccountStatus.PENDING_ACTIVATION
    assert Enrollment.objects.filter(
        class_section_id=class_id, user_id=created_user.pk, status="ACTIVE"
    ).exists()
    assert Enrollment.objects.filter(
        class_section_id=class_id, user_id=existing_student.pk, status="ACTIVE"
    ).exists()

    import_outbox = OutboxEvent.objects.filter(
        producer=OutboxProducer.IDENTITY,
        aggregate_id=str(created_user.pk),
        event_type="identity.student.imported",
    ).first()
    assert import_outbox is not None
    assert import_outbox.topic == "utask.identity.events"
    assert import_outbox.data["data"]["email"] == new_email
    assert import_outbox.data["data"]["student_id"] == new_mssv
    assert isinstance(import_outbox.data["data"]["secret"], dict)


# ---------------------------------------------------------------------------
# 4. Study groups, invite code, member operations, teacher adjust & recruitment queries
# ---------------------------------------------------------------------------


def test_study_groups_membership_transfer_adjust_and_discovery_queries(db):
    teacher = _create_user(roles=(GlobalRoleCode.TEACHER,))
    s1 = _create_user(roles=(GlobalRoleCode.STUDENT,), first_name="Mot", student_id="SV1001")
    s2 = _create_user(roles=(GlobalRoleCode.STUDENT,), first_name="Hai", student_id="SV1002")
    s3 = _create_user(roles=(GlobalRoleCode.STUDENT,), first_name="Ba", student_id="SV1003")
    s4 = _create_user(roles=(GlobalRoleCode.STUDENT,), first_name="Bon", student_id="SV1004")

    t_client = _client_for(teacher)
    c1, c2, c3, c4 = _client_for(s1), _client_for(s2), _client_for(s3), _client_for(s4)

    course = _create_course_api(t_client)
    section = _create_class_api(t_client, course["id"], group_min_size=2, group_max_size=4)
    class_id = section["id"]
    join_code, _ver = _issue_class_join_code(t_client, class_id, section["version"])
    for client in (c1, c2, c3, c4):
        _join_class_via_code(client, join_code)

    # Before joining any group, my-group returns data=None.
    my_empty = c1.get(f"/api/classroom/classes/{class_id}/my-group/")
    assert my_empty.status_code == 200
    assert my_empty.json()["data"] is None

    # Student 1 creates recruiting group A.
    create_g1 = c1.post(
        "/api/classroom/groups/",
        {
            "class_id": class_id,
            "name": "Nhóm Alpha",
            "is_recruiting": True,
            "recruitment_note": "Cần Backend Python",
            "needed_skills": ["Python", "PostgreSQL"],
        },
        format="json",
        **_idem(),
    )
    assert create_g1.status_code == 201
    g1 = create_g1.json()["data"]
    g1_id = g1["id"]
    g1_ver = g1["source_version"]
    assert g1["leader_id"] == str(s1.pk)
    assert g1["member_count"] == 1

    # Student 4 creates group B (not recruiting).
    create_g2 = c4.post(
        "/api/classroom/groups/",
        {"class_id": class_id, "name": "Nhóm Beta", "is_recruiting": False},
        format="json",
        **_idem(),
    )
    assert create_g2.status_code == 201
    g2_id = create_g2.json()["data"]["id"]

    # List groups (global and per-class).
    assert len(t_client.get(f"/api/classroom/classes/{class_id}/groups/").json()["data"]) == 2
    assert len(c1.get("/api/classroom/groups/").json()["data"]) == 2

    # Open groups & unassigned students queries.
    open_groups = c2.get(f"/api/classroom/classes/{class_id}/open-groups/", {"skill": "python"})
    assert open_groups.status_code == 200
    assert [g["id"] for g in open_groups.json()["data"]] == [g1_id]

    unassigned = c2.get(f"/api/classroom/classes/{class_id}/unassigned-students/")
    assert unassigned.status_code == 200
    unassigned_ids = {item["user_id"] for item in unassigned.json()["data"]}
    assert unassigned_ids == {str(s2.pk), str(s3.pk)}
    assert set(unassigned.json()["data"][0].keys()) == {
        "user_id",
        "display_name",
        "student_id",
        "avatar_url",
    }

    # Leader issues invite code and rotates it; Student 2 joins via rotated invite code.
    inv1 = c1.post(
        f"/api/classroom/groups/{g1_id}/invite-code/",
        {"version": g1_ver, "enabled": True},
        format="json",
        **_idem(),
    )
    assert inv1.status_code == 200
    g1_ver = inv1.json()["data"]["version"]

    inv2 = c1.post(
        f"/api/classroom/groups/{g1_id}/invite-code/",
        {"version": g1_ver, "enabled": True},
        format="json",
        **_idem(),
    )
    assert inv2.status_code == 200
    invite_code = inv2.json()["data"]["code"]
    g1_ver = inv2.json()["data"]["version"]

    joined = c2.post(
        "/api/classroom/groups/join/",
        {"code": invite_code},
        format="json",
        **_idem(),
    )
    assert joined.status_code == 201
    g1_ver = joined.json()["data"]["source_version"]
    assert joined.json()["data"]["member_count"] == 2

    # my-group query returns active group with role and members.
    my_group = c2.get(f"/api/classroom/classes/{class_id}/my-group/")
    assert my_group.status_code == 200
    assert my_group.json()["data"]["id"] == g1_id
    assert my_group.json()["data"]["my_role"] == "MEMBER"
    assert len(my_group.json()["data"]["members"]) == 2

    # Transfer leader s1 -> s2, then s1 leaves.
    transferred = c1.post(
        f"/api/classroom/groups/{g1_id}/transfer-leader/",
        {"version": g1_ver, "user_id": str(s2.pk), "reason": "Bàn giao trưởng nhóm"},
        format="json",
        **_idem(),
    )
    assert transferred.status_code == 200
    assert transferred.json()["data"]["leader_id"] == str(s2.pk)
    g1_ver = transferred.json()["data"]["source_version"]

    left = c1.post(
        f"/api/classroom/groups/{g1_id}/leave/",
        {"version": g1_ver, "reason": "Chuyển sang nhóm khác"},
        format="json",
        **_idem(),
    )
    assert left.status_code == 200
    assert left.json()["data"]["member_count"] == 1
    g1_ver = left.json()["data"]["source_version"]

    # Teacher adjusts unassigned s3 into group A, then leader s2 removes s3.
    assign_s3 = t_client.post(
        f"/api/classroom/classes/{class_id}/adjust-member/",
        {"user_id": str(s3.pk), "target_group_id": g1_id, "reason": "Phân bổ cân bằng nhóm"},
        format="json",
        **_idem(),
    )
    assert assign_s3.status_code == 200
    assert assign_s3.json()["data"] == {"user_id": str(s3.pk), "group_id": g1_id}
    g1_ver = t_client.get(f"/api/classroom/groups/{g1_id}/").json()["data"]["source_version"]

    removed = c2.post(
        f"/api/classroom/groups/{g1_id}/remove-member/",
        {"version": g1_ver, "user_id": str(s3.pk), "reason": "Không tham gia họp nhóm"},
        format="json",
        **_idem(),
    )
    assert removed.status_code == 200
    assert removed.json()["data"]["member_count"] == 1

    # Teacher adjusts s1 into group B, then removes s1 from group B (target_group_id=None).
    move_s1 = t_client.post(
        f"/api/classroom/classes/{class_id}/adjust-member/",
        {"user_id": str(s1.pk), "target_group_id": g2_id, "reason": "Chuyển vào Nhóm Beta"},
        format="json",
        **_idem(),
    )
    assert move_s1.status_code == 200
    assert move_s1.json()["data"]["group_id"] == g2_id

    unassign_s1 = t_client.post(
        f"/api/classroom/classes/{class_id}/adjust-member/",
        {"user_id": str(s1.pk), "target_group_id": None, "reason": "Tạm tách khỏi nhóm"},
        format="json",
        **_idem(),
    )
    assert unassign_s1.status_code == 200
    assert unassign_s1.json()["data"]["group_id"] is None

    # Member history endpoint retains LEFT/REMOVED memberships; sole leader dissolve check works.
    members_hist = t_client.get(f"/api/classroom/groups/{g1_id}/members/")
    assert members_hist.status_code == 200
    assert {m["status"] for m in members_hist.json()["data"]} == {"ACTIVE", "LEFT", "REMOVED"}

    g1_ver = c2.get(f"/api/classroom/groups/{g1_id}/").json()["data"]["source_version"]
    sole_blocked = c2.post(
        f"/api/classroom/groups/{g1_id}/leave/",
        {"version": g1_ver, "reason": "Rời nhóm duy nhất"},
        format="json",
        **_idem(),
    )
    assert sole_blocked.status_code == 409
    assert sole_blocked.json()["error"]["code"] == "SOLE_LEADER_DISSOLVE_REQUIRED"

    dissolved = c2.post(
        f"/api/classroom/groups/{g1_id}/leave/",
        {"version": g1_ver, "reason": "Giải thể nhóm", "dissolve_if_sole_member": True},
        format="json",
        **_idem(),
    )
    assert dissolved.status_code == 200
    assert dissolved.json()["data"]["status"] == "ARCHIVED"


# ---------------------------------------------------------------------------
# 5. Join requests (create, duplicate 409, list, cancel, reject, approve, my-join-requests)
# ---------------------------------------------------------------------------


def test_group_join_requests_full_workflow_and_duplicate_conflict(db):
    teacher = _create_user(roles=(GlobalRoleCode.TEACHER,))
    leader1 = _create_user(roles=(GlobalRoleCode.STUDENT,))
    leader2 = _create_user(roles=(GlobalRoleCode.STUDENT,))
    applicant_a = _create_user(roles=(GlobalRoleCode.STUDENT,))
    applicant_b = _create_user(roles=(GlobalRoleCode.STUDENT,))

    t_client = _client_for(teacher)
    l1_client, l2_client = _client_for(leader1), _client_for(leader2)
    a_client, b_client = _client_for(applicant_a), _client_for(applicant_b)

    course = _create_course_api(t_client)
    section = _create_class_api(t_client, course["id"], group_min_size=2, group_max_size=4)
    class_id = section["id"]
    join_code, _ver = _issue_class_join_code(t_client, class_id, section["version"])
    for client in (l1_client, l2_client, a_client, b_client):
        _join_class_via_code(client, join_code)

    g1_id = l1_client.post(
        "/api/classroom/groups/",
        {"class_id": class_id, "name": "Nhóm Tuyển 1", "is_recruiting": True},
        format="json",
        **_idem(),
    ).json()["data"]["id"]
    g2_id = l2_client.post(
        "/api/classroom/groups/",
        {"class_id": class_id, "name": "Nhóm Tuyển 2", "is_recruiting": True},
        format="json",
        **_idem(),
    ).json()["data"]["id"]

    # Applicant A creates a join request to Group 1.
    req1_resp = a_client.post(
        f"/api/classroom/groups/{g1_id}/join-requests/",
        {"message": "Mình làm tốt Django"},
        format="json",
        **_idem(),
    )
    assert req1_resp.status_code == 201
    req1_id = req1_resp.json()["data"]["id"]
    assert req1_resp.json()["data"]["status"] == "PENDING"

    # Second pending join request in the same class (even to Group 2) -> 409.
    dup_req = a_client.post(
        f"/api/classroom/groups/{g2_id}/join-requests/",
        {"message": "Xin vào thêm nhóm 2"},
        format="json",
        **_idem(),
    )
    assert dup_req.status_code == 409
    assert dup_req.json()["error"]["code"] == "PENDING_JOIN_REQUEST_EXISTS"

    # List group join requests (leader) & my-join-requests (applicant).
    group_reqs = l1_client.get(f"/api/classroom/groups/{g1_id}/join-requests/")
    assert group_reqs.status_code == 200
    assert [r["id"] for r in group_reqs.json()["data"]] == [req1_id]

    my_reqs = a_client.get(f"/api/classroom/classes/{class_id}/my-join-requests/")
    assert my_reqs.status_code == 200
    assert [r["id"] for r in my_reqs.json()["data"]] == [req1_id]

    # Applicant A cancels req1, then re-applies to Group 1 and gets REJECTED.
    cancelled = a_client.post(
        f"/api/classroom/groups/{g1_id}/join-requests/{req1_id}/cancel/",
        {},
        format="json",
        **_idem(),
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "CANCELLED"

    req2_id = a_client.post(
        f"/api/classroom/groups/{g1_id}/join-requests/",
        {"message": "Xin ứng tuyển lại"},
        format="json",
        **_idem(),
    ).json()["data"]["id"]
    rejected = l1_client.post(
        f"/api/classroom/groups/{g1_id}/join-requests/{req2_id}/reject/",
        {"review_note": "Nhóm cần kỹ năng Frontend"},
        format="json",
        **_idem(),
    )
    assert rejected.status_code == 200
    assert rejected.json()["data"]["status"] == "REJECTED"
    assert rejected.json()["data"]["review_note"] == "Nhóm cần kỹ năng Frontend"

    # Applicant B applies to Group 1 and gets APPROVED -> becomes ACTIVE member.
    req_b_id = b_client.post(
        f"/api/classroom/groups/{g1_id}/join-requests/",
        {"message": "Mình làm Frontend React"},
        format="json",
        **_idem(),
    ).json()["data"]["id"]
    approved = l1_client.post(
        f"/api/classroom/groups/{g1_id}/join-requests/{req_b_id}/approve/",
        {"review_note": "Chào mừng vào nhóm"},
        format="json",
        **_idem(),
    )
    assert approved.status_code == 200
    assert approved.json()["data"]["status"] == "APPROVED"

    g1_detail = l1_client.get(f"/api/classroom/groups/{g1_id}/").json()["data"]
    assert g1_detail["member_count"] == 2
    assert GroupMember.objects.filter(
        group_id=g1_id, enrollment__user_id=applicant_b.pk, status="ACTIVE", role="MEMBER"
    ).exists()


# ---------------------------------------------------------------------------
# 6. Topic proposals (draft upsert, submit, teacher review) & Classroom activities
# ---------------------------------------------------------------------------


def test_topic_proposals_review_states_and_classroom_activities(db):
    teacher = _create_user(roles=(GlobalRoleCode.TEACHER,))
    leader1 = _create_user(roles=(GlobalRoleCode.STUDENT,))
    leader2 = _create_user(roles=(GlobalRoleCode.STUDENT,))

    t_client = _client_for(teacher)
    l1_client, l2_client = _client_for(leader1), _client_for(leader2)

    course = _create_course_api(t_client)
    section = _create_class_api(t_client, course["id"], group_min_size=1, group_max_size=4)
    class_id = section["id"]
    join_code, _ver = _issue_class_join_code(t_client, class_id, section["version"])
    _join_class_via_code(l1_client, join_code)
    _join_class_via_code(l2_client, join_code)

    g1_id = l1_client.post(
        "/api/classroom/groups/",
        {"class_id": class_id, "name": "Nhóm Đề Tài 1"},
        format="json",
        **_idem(),
    ).json()["data"]["id"]
    g2_id = l2_client.post(
        "/api/classroom/groups/",
        {"class_id": class_id, "name": "Nhóm Đề Tài 2"},
        format="json",
        **_idem(),
    ).json()["data"]["id"]

    # Initially no topic proposal -> data=None.
    initial = l1_client.get(f"/api/classroom/groups/{g1_id}/topic/")
    assert initial.status_code == 200
    assert initial.json()["data"] is None

    # Create draft (201) and update draft (200).
    draft = l1_client.put(
        f"/api/classroom/groups/{g1_id}/topic/",
        {
            "title": "Hệ thống quản lý đồ án",
            "summary": "Bản nháp lần 1",
            "objectives": "Xây dựng quản lý nhiệm vụ",
        },
        format="json",
    )
    assert draft.status_code == 201
    ver = draft.json()["data"]["version"]
    assert draft.json()["data"]["status"] == "DRAFT"

    updated = l1_client.put(
        f"/api/classroom/groups/{g1_id}/topic/",
        {
            "title": "Hệ thống quản lý đồ án UTask",
            "summary": "Bản nháp lần 2 đầy đủ hơn",
            "objectives": "Quản lý sprint và task",
            "version": ver,
        },
        format="json",
    )
    assert updated.status_code == 200
    ver = updated.json()["data"]["version"]

    # Submit -> PENDING.
    submitted = l1_client.post(
        f"/api/classroom/groups/{g1_id}/topic/submit/",
        {"version": ver},
        format="json",
        **_idem(),
    )
    assert submitted.status_code == 200
    assert submitted.json()["data"]["status"] == "PENDING"
    ver = submitted.json()["data"]["version"]

    # Missing feedback on REVISION_REQUESTED -> 400.
    bad_review = t_client.post(
        f"/api/classroom/groups/{g1_id}/topic/review/",
        {"decision": "REVISION_REQUESTED", "version": ver},
        format="json",
        **_idem(),
    )
    assert bad_review.status_code == 400

    # Teacher requests revision -> leader updates & resubmits.
    rev = t_client.post(
        f"/api/classroom/groups/{g1_id}/topic/review/",
        {
            "decision": "REVISION_REQUESTED",
            "feedback": "Bổ sung phạm vi kiểm thử",
            "version": ver,
        },
        format="json",
        **_idem(),
    )
    assert rev.status_code == 200
    assert rev.json()["data"]["status"] == "REVISION_REQUESTED"
    ver = rev.json()["data"]["version"]

    revised = l1_client.put(
        f"/api/classroom/groups/{g1_id}/topic/",
        {
            "title": "UTask v2",
            "summary": "Đã bổ sung phạm vi kiểm thử",
            "objectives": "CI + E2E",
            "version": ver,
        },
        format="json",
    )
    assert revised.status_code == 200
    assert revised.json()["data"]["status"] == "DRAFT"
    ver = revised.json()["data"]["version"]

    ver = l1_client.post(
        f"/api/classroom/groups/{g1_id}/topic/submit/",
        {"version": ver},
        format="json",
        **_idem(),
    ).json()["data"]["version"]

    # Teacher rejects -> leader edits & resubmits -> teacher approves.
    rejected = t_client.post(
        f"/api/classroom/groups/{g1_id}/topic/review/",
        {"decision": "REJECTED", "feedback": "Trùng lặp đề tài cũ", "version": ver},
        format="json",
        **_idem(),
    )
    assert rejected.status_code == 200
    assert rejected.json()["data"]["status"] == "REJECTED"
    ver = rejected.json()["data"]["version"]

    ver = l1_client.put(
        f"/api/classroom/groups/{g1_id}/topic/",
        {
            "title": "UTask Core Monolith",
            "summary": "Đề tài mới hoàn toàn",
            "objectives": "Kiến trúc mô-đun",
            "version": ver,
        },
        format="json",
    ).json()["data"]["version"]
    ver = l1_client.post(
        f"/api/classroom/groups/{g1_id}/topic/submit/",
        {"version": ver},
        format="json",
        **_idem(),
    ).json()["data"]["version"]

    approved = t_client.post(
        f"/api/classroom/groups/{g1_id}/topic/review/",
        {"decision": "APPROVED", "feedback": "Đồng ý triển khai", "version": ver},
        format="json",
        **_idem(),
    )
    assert approved.status_code == 200
    assert approved.json()["data"]["status"] == "APPROVED"
    ver = approved.json()["data"]["version"]

    # Cannot edit an APPROVED topic.
    locked_edit = l1_client.put(
        f"/api/classroom/groups/{g1_id}/topic/",
        {"title": "Illegal Edit", "summary": "Nope", "version": ver},
        format="json",
    )
    assert locked_edit.status_code == 409
    assert locked_edit.json()["error"]["code"] == "TOPIC_NOT_EDITABLE"

    # Classroom activities: class-level endpoint returns mutations & supports verb/actor filters.
    class_acts = t_client.get(f"/api/classroom/classes/{class_id}/activities/")
    assert class_acts.status_code == 200
    class_verbs = {row["verb"] for row in class_acts.json()["data"]}
    assert {
        "class.created",
        "class.code.changed",
        "enrollment.joined",
        "group.created",
        "group.topic.created",
        "group.topic.submitted",
        "group.topic.reviewed",
    }.issubset(class_verbs)

    filtered_acts = t_client.get(
        f"/api/classroom/classes/{class_id}/activities/",
        {"verb": "group.topic.reviewed", "actor_user_id": str(teacher.pk)},
    )
    assert filtered_acts.status_code == 200
    assert len(filtered_acts.json()["data"]) == 3
    assert all(row["verb"] == "group.topic.reviewed" for row in filtered_acts.json()["data"])

    # Group-level activities isolate Group 1 records (excludes class-level & Group 2 records).
    group1_acts = l1_client.get(f"/api/classroom/groups/{g1_id}/activities/")
    assert group1_acts.status_code == 200
    g1_rows = group1_acts.json()["data"]
    assert any(row["verb"] == "group.topic.reviewed" for row in g1_rows)
    assert all(row["subject_type"] != "ClassSection" for row in g1_rows)
    assert all(row["subject_id"] != g2_id for row in g1_rows)
    assert ClassroomActivity.objects.filter(class_section_id=class_id).count() >= len(g1_rows)


# ---------------------------------------------------------------------------
# 7. PostgreSQL composite deferrable FK check (0002_same_class_foreign_keys)
# ---------------------------------------------------------------------------


@pytest.mark.postgres
def test_composite_deferrable_fk_rejects_cross_class_group_member_at_commit(transactional_db):
    _ensure_roles()
    course = Course.objects.create(code=f"FK{uuid4().hex[:6].upper()}", name="DB Constraints")
    today = date.today()
    class_a = ClassSection.objects.create(
        course=course,
        code=f"CLSA{uuid4().hex[:5].upper()}",
        name="Class A",
        term="2026-1",
        starts_on=today,
        ends_on=today + timedelta(days=60),
    )
    class_b = ClassSection.objects.create(
        course=course,
        code=f"CLSB{uuid4().hex[:5].upper()}",
        name="Class B",
        term="2026-1",
        starts_on=today,
        ends_on=today + timedelta(days=60),
    )
    group_a = StudyGroup.objects.create(class_section=class_a, name="Group in A")
    enrollment_b = Enrollment.objects.create(class_section=class_b, user_id=uuid4())

    # Attempting to insert GroupMember referencing Enrollment from a DIFFERENT ClassSection
    # passes the INSERT statement (DEFERRABLE INITIALLY DEFERRED) and fails at COMMIT!
    inserted_before_commit = False
    with pytest.raises(IntegrityError) as exc_info:
        with transaction.atomic():
            GroupMember.objects.create(
                class_section=class_a,
                group=group_a,
                enrollment=enrollment_b,
                role="MEMBER",
            )
            inserted_before_commit = True
    assert inserted_before_commit is True
    assert (
        getattr(getattr(exc_info.value.__cause__, "diag", None), "constraint_name", None)
        == "fk_group_member_same_class_enrollment"
    )
    assert not GroupMember.objects.filter(group=group_a, enrollment=enrollment_b).exists()

    # Mirror check: referencing StudyGroup from Class A with Class B fails at COMMIT on group FK.
    inserted_group_fk = False
    with pytest.raises(IntegrityError) as grp_exc:
        with transaction.atomic():
            GroupMember.objects.create(
                class_section=class_b,
                group=group_a,
                enrollment=enrollment_b,
                role="MEMBER",
            )
            inserted_group_fk = True
    assert inserted_group_fk is True
    assert (
        getattr(getattr(grp_exc.value.__cause__, "diag", None), "constraint_name", None)
        == "fk_group_member_same_class_group"
    )
