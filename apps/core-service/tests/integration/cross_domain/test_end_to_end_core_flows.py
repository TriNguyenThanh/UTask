"""End-to-end ACID integration tests across Identity, Classroom, and Work with zero mocks."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import uuid4

import pytest
from allauth.account.models import EmailAddress
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import AccountStatus, User, UserProfile, UserSession
from apps.courses.models import Enrollment
from apps.groups.models import GroupMember, GroupProjectLink, StudyGroup
from apps.messaging.models import OutboxEvent, OutboxProducer
from apps.projects.models import Project, ProjectMember

pytestmark = pytest.mark.integration

TEST_PASSWORD = "StrongPassword123!"


def _idem_headers(key: str | None = None) -> dict[str, str]:
    return {"HTTP_IDEMPOTENCY_KEY": key or str(uuid4())}


def _create_verified_user(
    *,
    first_name: str,
    last_name: str,
    role: str = "STUDENT",
    student_id: str | None = None,
) -> User:
    suffix = uuid4().hex[:8]
    user = User.objects.create_user(
        email=f"{role.lower()}_{suffix}@utask.edu.vn",
        username=f"{role.lower()}_{suffix}",
        password=TEST_PASSWORD,
        student_id=student_id,
        first_name=first_name,
        last_name=last_name,
        global_role_code=role,
        account_status=AccountStatus.ACTIVE,
    )
    EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
    return user


def _login_as(user: User, password: str = TEST_PASSWORD) -> APIClient:
    login_client = APIClient()
    response = login_client.post(
        "/api/auth/login",
        {"email": user.email, "password": password},
        format="json",
    )
    assert response.status_code == 200, response.content
    access_token = response.json()["data"]["access"]
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    client.user = user
    client.access_token = access_token
    return client


def _create_course_and_class(teacher_client: APIClient) -> tuple[dict[str, Any], dict[str, Any]]:
    course_resp = teacher_client.post(
        "/api/classroom/courses/",
        {"code": f"CS{uuid4().hex[:6].upper()}", "name": "Distributed Systems"},
        format="json",
        **_idem_headers(),
    )
    assert course_resp.status_code == 201, course_resp.content
    course_data = course_resp.json()["data"]

    today = date.today()
    class_resp = teacher_client.post(
        "/api/classroom/classes/",
        {
            "course_id": course_data["id"],
            "code": f"SE-{uuid4().hex[:6].upper()}",
            "name": "SE-2026 Class 01",
            "term": "2026-HK1",
            "starts_on": (today - timedelta(days=3)).isoformat(),
            "ends_on": (today + timedelta(days=120)).isoformat(),
            "group_min_size": 1,
            "group_max_size": 5,
        },
        format="json",
        **_idem_headers(),
    )
    assert class_resp.status_code == 201, class_resp.content
    return course_data, class_resp.json()["data"]


def test_classroom_student_provisioning_creates_identity_users_enrollments_and_outbox(db, settings):
    settings.IDENTITY_REQUIRE_EMAIL_ACTIVATION = True

    teacher = _create_verified_user(first_name="Hoa", last_name="Le", role="TEACHER")
    teacher_client = _login_as(teacher)
    _course, section = _create_course_and_class(teacher_client)
    class_id = section["id"]

    suffix = uuid4().hex[:6]
    student1_email = f"student1_{suffix}@utask.edu.vn"
    student1_sid = f"SV{suffix.upper()}1"
    student2_email = f"student2_{suffix}@utask.edu.vn"
    student2_sid = f"SV{suffix.upper()}2"

    prov_resp = teacher_client.post(
        f"/api/classroom/classes/{class_id}/students/",
        {
            "students": [
                {
                    "row_number": 1,
                    "email": student1_email,
                    "student_id": student1_sid,
                    "first_name": "Mai",
                    "last_name": "Pham",
                },
                {
                    "row_number": 2,
                    "email": student2_email,
                    "student_id": student2_sid,
                    "first_name": "Nam",
                    "last_name": "Do",
                },
            ]
        },
        format="json",
        **_idem_headers(),
    )
    assert prov_resp.status_code == 200, prov_resp.content
    body = prov_resp.json()["data"]
    assert body["summary"]["created_accounts"] == 2
    assert body["summary"]["enrolled"] == 2
    assert body["summary"]["failed"] == 0

    for row, expected_email, expected_name in (
        (body["results"][0], student1_email, "Pham Mai"),
        (body["results"][1], student2_email, "Do Nam"),
    ):
        user = User.objects.get(pk=row["user_id"])
        assert user.email == expected_email
        assert user.account_status == AccountStatus.PENDING_ACTIVATION
        profile = UserProfile.objects.get(user=user)
        assert profile.display_name == expected_name
        assert Enrollment.objects.filter(
            class_section_id=class_id, user_id=user.pk, status="ACTIVE"
        ).exists()

        outbox_row = OutboxEvent.objects.filter(
            producer=OutboxProducer.IDENTITY,
            event_type="identity.student.imported",
            aggregate_id=str(user.pk),
        ).first()
        assert outbox_row is not None
        assert outbox_row.data["producer"] == "identity-service"
        assert outbox_row.data["data"]["email"] == expected_email
        assert outbox_row.data["data"]["student_id"] == user.student_id
        assert "secret" in outbox_row.data["data"]


def test_study_group_project_creation_creates_immediate_classroom_project_link(db):
    teacher = _create_verified_user(first_name="Khang", last_name="Vo", role="TEACHER")
    leader = _create_verified_user(
        first_name="Linh",
        last_name="Nguyen",
        role="STUDENT",
        student_id=f"SV{uuid4().hex[:6].upper()}",
    )
    teacher_client = _login_as(teacher)
    leader_client = _login_as(leader)
    _course, section = _create_course_and_class(teacher_client)
    class_id = section["id"]

    # Enroll existing active student through Classroom students endpoint.
    enroll_resp = teacher_client.post(
        f"/api/classroom/classes/{class_id}/students/",
        {"students": [{"row_number": 1, "email": leader.email}]},
        format="json",
        **_idem_headers(),
    )
    assert enroll_resp.status_code == 200, enroll_resp.content
    assert enroll_resp.json()["data"]["summary"]["enrolled"] == 1

    # Leader creates StudyGroup in Classroom.
    group_resp = leader_client.post(
        "/api/classroom/groups/",
        {"class_id": class_id, "name": "Group Nova"},
        format="json",
        **_idem_headers(),
    )
    assert group_resp.status_code == 201, group_resp.content
    group_id = group_resp.json()["data"]["id"]

    # Leader creates Work Project for that StudyGroup.
    project_resp = leader_client.post(
        "/api/work/projects/",
        {
            "identifier": f"NV{uuid4().hex[:5].upper()}",
            "name": "Nova Platform",
            "classroom_group_id": group_id,
        },
        format="json",
        **_idem_headers(),
    )
    assert project_resp.status_code == 201, project_resp.content
    project_id = project_resp.json()["data"]["id"]

    # Immediately visible in Classroom without any async event relay.
    links_resp = leader_client.get(f"/api/classroom/groups/{group_id}/projects/")
    assert links_resp.status_code == 200, links_resp.content
    links = links_resp.json()["data"]
    assert len(links) == 1
    assert links[0]["project_id"] == project_id
    assert links[0]["group_id"] == group_id
    assert links[0]["class_section_id"] == class_id
    assert GroupProjectLink.objects.filter(group_id=group_id, project_id=project_id).exists()


def test_classroom_membership_mutations_sync_work_project_members_in_same_transaction(db):
    teacher = _create_verified_user(first_name="Quang", last_name="Bui", role="TEACHER")
    student_a = _create_verified_user(
        first_name="Duc",
        last_name="Hoang",
        role="STUDENT",
        student_id=f"SV{uuid4().hex[:6].upper()}",
    )
    student_b = _create_verified_user(
        first_name="Huy",
        last_name="Dang",
        role="STUDENT",
        student_id=f"SV{uuid4().hex[:6].upper()}",
    )
    student_c = _create_verified_user(
        first_name="Khanh",
        last_name="Vu",
        role="STUDENT",
        student_id=f"SV{uuid4().hex[:6].upper()}",
    )
    teacher_client = _login_as(teacher)
    client_a = _login_as(student_a)
    client_b = _login_as(student_b)
    _client_c = _login_as(student_c)

    _course, section = _create_course_and_class(teacher_client)
    class_id = section["id"]

    enroll_resp = teacher_client.post(
        f"/api/classroom/classes/{class_id}/students/",
        {
            "students": [
                {"row_number": 1, "email": student_a.email},
                {"row_number": 2, "email": student_b.email},
                {"row_number": 3, "email": student_c.email},
            ]
        },
        format="json",
        **_idem_headers(),
    )
    assert enroll_resp.status_code == 200, enroll_resp.content

    # Student A creates Group 1 and Work Project 1.
    group_resp = client_a.post(
        "/api/classroom/groups/",
        {"class_id": class_id, "name": "Sync Squad"},
        format="json",
        **_idem_headers(),
    )
    assert group_resp.status_code == 201, group_resp.content
    group = group_resp.json()["data"]
    group_id = group["id"]

    project_resp = client_a.post(
        "/api/work/projects/",
        {
            "identifier": f"SY{uuid4().hex[:5].upper()}",
            "name": "ACID Sync Project",
            "classroom_group_id": group_id,
        },
        format="json",
        **_idem_headers(),
    )
    assert project_resp.status_code == 201, project_resp.content
    project_id = project_resp.json()["data"]["id"]

    # 1) New student joins group -> Work ProjectMember immediately adds student_b.
    code_resp = client_a.post(
        f"/api/classroom/groups/{group_id}/invite-code/",
        {"version": group["source_version"], "enabled": True},
        format="json",
        **_idem_headers(),
    )
    assert code_resp.status_code == 200, code_resp.content
    invite_code = code_resp.json()["data"]["code"]

    join_resp = client_b.post(
        "/api/classroom/groups/join/",
        {"code": invite_code},
        format="json",
        **_idem_headers(),
    )
    assert join_resp.status_code == 201, join_resp.content
    group_ver = join_resp.json()["data"]["source_version"]

    work_members = {
        row.user_id: (row.role, row.status)
        for row in ProjectMember.objects.filter(project_id=project_id)
    }
    assert work_members == {
        student_a.pk: ("LEADER", "ACTIVE"),
        student_b.pk: ("MEMBER", "ACTIVE"),
    }
    assert Project.objects.get(pk=project_id).group_source_version == group_ver
    assert client_b.get(f"/api/work/projects/{project_id}/").status_code == 200

    # 2) Leader transfers leadership to student_b -> Work roles swap immediately.
    transfer_resp = client_a.post(
        f"/api/classroom/groups/{group_id}/transfer-leader/",
        {
            "version": group_ver,
            "user_id": str(student_b.pk),
            "reason": "Rotating team lead",
        },
        format="json",
        **_idem_headers(),
    )
    assert transfer_resp.status_code == 200, transfer_resp.content
    group_ver = transfer_resp.json()["data"]["source_version"]

    work_members = {
        row.user_id: (row.role, row.status)
        for row in ProjectMember.objects.filter(project_id=project_id)
    }
    assert work_members == {
        student_a.pk: ("MEMBER", "ACTIVE"),
        student_b.pk: ("LEADER", "ACTIVE"),
    }

    # 3) Student A leaves group -> Work marks student_a LEFT and revokes project read access.
    leave_resp = client_a.post(
        f"/api/classroom/groups/{group_id}/leave/",
        {"version": group_ver, "reason": "Switching to another squad"},
        format="json",
        **_idem_headers(),
    )
    assert leave_resp.status_code == 200, leave_resp.content
    group_ver = leave_resp.json()["data"]["source_version"]

    member_a = ProjectMember.objects.get(project_id=project_id, user_id=student_a.pk)
    assert member_a.status == "LEFT"
    assert member_a.left_at is not None
    assert client_a.get(f"/api/work/projects/{project_id}/").status_code == 404

    # 4) Teacher adjusts student_c into group -> Work immediately adds student_c ACTIVE.
    adjust_resp = teacher_client.post(
        f"/api/classroom/classes/{class_id}/adjust-member/",
        {
            "user_id": str(student_c.pk),
            "target_group_id": group_id,
            "reason": "Balancing group workload",
        },
        format="json",
        **_idem_headers(),
    )
    assert adjust_resp.status_code == 200, adjust_resp.content

    study_group = StudyGroup.objects.get(pk=group_id)
    project_row = Project.objects.get(pk=project_id)
    assert project_row.group_source_version == study_group.source_version
    assert ProjectMember.objects.filter(
        project_id=project_id, user_id=student_c.pk, role="MEMBER", status="ACTIVE"
    ).exists()

    # 5) ACID rollback check: if Work membership sync raises, Classroom GroupMember rolls back too.
    # Verify rollback via atomic savepoint failure in publish_membership -> sync_group_membership.
    initial_group_ver = study_group.source_version
    initial_active_count = GroupMember.objects.filter(group_id=group_id, status="ACTIVE").count()

    from apps.projects import interface as projects_interface

    original_sync = projects_interface.sync_group_membership

    def _boom(*args, **kwargs):
        raise RuntimeError("Simulated sync failure")

    projects_interface.sync_group_membership = _boom
    try:
        failed_adjust = teacher_client.post(
            f"/api/classroom/classes/{class_id}/adjust-member/",
            {
                "user_id": str(student_a.pk),
                "target_group_id": group_id,
                "reason": "Rollback verification",
            },
            format="json",
            **_idem_headers(),
        )
    finally:
        projects_interface.sync_group_membership = original_sync

    assert failed_adjust.status_code == 500
    assert failed_adjust.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    study_group.refresh_from_db()
    assert study_group.source_version == initial_group_ver
    active_after_rollback = GroupMember.objects.filter(group_id=group_id, status="ACTIVE").count()
    assert active_after_rollback == initial_active_count


def test_identity_profile_update_reflected_immediately_in_work_members_and_activities(db):
    teacher = _create_verified_user(first_name="Thu", last_name="Dao", role="TEACHER")
    leader = _create_verified_user(
        first_name="An",
        last_name="Nguyen",
        role="STUDENT",
        student_id=f"SV{uuid4().hex[:6].upper()}",
    )
    teacher_client = _login_as(teacher)
    leader_client = _login_as(leader)
    _course, section = _create_course_and_class(teacher_client)

    assert (
        teacher_client.post(
            f"/api/classroom/classes/{section['id']}/students/",
            {"students": [{"row_number": 1, "email": leader.email}]},
            format="json",
            **_idem_headers(),
        ).status_code
        == 200
    )
    group_id = leader_client.post(
        "/api/classroom/groups/",
        {"class_id": section["id"], "name": "Profile Live Team"},
        format="json",
        **_idem_headers(),
    ).json()["data"]["id"]

    project_id = leader_client.post(
        "/api/work/projects/",
        {
            "identifier": f"PR{uuid4().hex[:5].upper()}",
            "name": "Live Profile Project",
            "classroom_group_id": group_id,
        },
        format="json",
        **_idem_headers(),
    ).json()["data"]["id"]

    # Initial display_name in Work endpoints.
    members_before = leader_client.get(f"/api/work/projects/{project_id}/members/")
    assert members_before.status_code == 200
    assert members_before.json()["data"][0]["display_name"] == "Nguyen An"

    acts_before = leader_client.get(f"/api/work/projects/{project_id}/activities/")
    assert acts_before.status_code == 200
    assert acts_before.json()["data"][0]["actor_display_name"] == "Nguyen An"

    # Update Identity profile via PATCH /api/auth/users/me -> Postgres trigger updates display_name.
    patch_profile = leader_client.patch(
        "/api/auth/users/me",
        {"first_name": "Minh", "last_name": "Tran"},
        format="json",
    )
    assert patch_profile.status_code == 200, patch_profile.content
    assert patch_profile.json()["data"]["display_name"] == "Tran Minh"

    # Immediately reflected in Work members & activities with zero projection sync delay.
    members_after = leader_client.get(f"/api/work/projects/{project_id}/members/")
    assert members_after.status_code == 200
    assert members_after.json()["data"][0]["display_name"] == "Tran Minh"

    acts_after = leader_client.get(f"/api/work/projects/{project_id}/activities/")
    assert acts_after.status_code == 200
    assert all(
        row["actor_display_name"] == "Tran Minh"
        for row in acts_after.json()["data"]
        if row["actor_user_id"] == str(leader.pk)
    )


def test_teacher_feedback_mention_outbox_and_notification_internal_resolution(db, settings):
    teacher = _create_verified_user(first_name="Giang", last_name="Ho", role="TEACHER")
    leader = _create_verified_user(
        first_name="Khue",
        last_name="Ly",
        role="STUDENT",
        student_id=f"SV{uuid4().hex[:6].upper()}",
    )
    member = _create_verified_user(
        first_name="Phat",
        last_name="Truong",
        role="STUDENT",
        student_id=f"SV{uuid4().hex[:6].upper()}",
    )
    teacher_client = _login_as(teacher)
    leader_client = _login_as(leader)
    member_client = _login_as(member)

    _course, section = _create_course_and_class(teacher_client)
    class_id = section["id"]
    assert (
        teacher_client.post(
            f"/api/classroom/classes/{class_id}/students/",
            {
                "students": [
                    {"row_number": 1, "email": leader.email},
                    {"row_number": 2, "email": member.email},
                ]
            },
            format="json",
            **_idem_headers(),
        ).status_code
        == 200
    )
    group = leader_client.post(
        "/api/classroom/groups/",
        {"class_id": class_id, "name": "Feedback Team"},
        format="json",
        **_idem_headers(),
    ).json()["data"]
    group_id = group["id"]
    invite_code = leader_client.post(
        f"/api/classroom/groups/{group_id}/invite-code/",
        {"version": group["source_version"], "enabled": True},
        format="json",
        **_idem_headers(),
    ).json()["data"]["code"]
    assert (
        member_client.post(
            "/api/classroom/groups/join/",
            {"code": invite_code},
            format="json",
            **_idem_headers(),
        ).status_code
        == 201
    )

    project = leader_client.post(
        "/api/work/projects/",
        {
            "identifier": f"FB{uuid4().hex[:5].upper()}",
            "name": "Feedback Verified Project",
            "classroom_group_id": group_id,
        },
        format="json",
        **_idem_headers(),
    ).json()["data"]
    project_id = project["id"]

    task = leader_client.post(
        f"/api/work/projects/{project_id}/tasks/",
        {"title": "Deliver Sprint Demo"},
        format="json",
        **_idem_headers(),
    ).json()["data"]
    task_id = task["id"]

    # Teacher posts feedback mentioning member -> live verified via apps.groups.interface.
    fb_resp = teacher_client.post(
        "/api/work/comments/",
        {
            "task_id": task_id,
            "content_html": (
                f'<p>Great job <mention-component data-id="{member.pk}">@Phat</mention-component>'
                ", please add test metrics.</p>"
            ),
        },
        format="json",
    )
    assert fb_resp.status_code == 201, fb_resp.content
    comment_data = fb_resp.json()["data"]
    comment_id = comment_data["id"]
    assert comment_data["is_teacher_feedback"] is True
    assert comment_data["mentioned_user_ids"] == [str(member.pk)]

    # Verify work-service outbox events emitted in the same transaction.
    feedback_outbox = OutboxEvent.objects.get(
        producer=OutboxProducer.WORK,
        event_type="teacher.feedback.added",
        aggregate_id=comment_id,
    )
    mention_outbox = OutboxEvent.objects.get(
        producer=OutboxProducer.WORK,
        event_type="comment.mentions.added",
        aggregate_id=comment_id,
    )
    assert feedback_outbox.data["producer"] == "work-service"
    assert str(member.pk) in feedback_outbox.data["data"]["recipient_ids"]
    assert mention_outbox.data["data"]["recipient_ids"] == [str(member.pk)]

    # Notification internal resolve endpoint resolves eligible=True immediately.
    notif_client = APIClient()
    notif_headers = {"HTTP_X_SERVICE_TOKEN": settings.NOTIFICATION_SERVICE_TOKEN}

    resolve_fb = notif_client.post(
        "/api/v1/internal/notifications/resolve",
        {
            "user_id": str(member.pk),
            "event_type": "teacher.feedback.added",
            "project_id": project_id,
            "data": {"comment_id": comment_id, "actor_user_id": str(teacher.pk)},
        },
        format="json",
        **notif_headers,
    )
    assert resolve_fb.status_code == 200, resolve_fb.content
    fb_res = resolve_fb.json()
    assert fb_res["eligible"] is True
    assert fb_res["target"]["kind"] == "board-issue"
    assert fb_res["target"]["projectId"] == project_id

    resolve_mention = notif_client.post(
        "/api/v1/internal/notifications/resolve",
        {
            "items": [
                {
                    "user_id": str(member.pk),
                    "event_type": "comment.mentions.added",
                    "project_id": project_id,
                    "data": {"comment_id": comment_id, "actor_user_id": str(teacher.pk)},
                },
                {
                    "user_id": str(leader.pk),
                    "event_type": "comment.mentions.added",
                    "project_id": project_id,
                    "data": {"comment_id": comment_id, "actor_user_id": str(teacher.pk)},
                },
            ]
        },
        format="json",
        **notif_headers,
    )
    assert resolve_mention.status_code == 200, resolve_mention.content
    results = resolve_mention.json()["results"]
    assert results[0]["eligible"] is True
    assert results[1]["eligible"] is False

    # Notification internal contacts endpoint resolves live Identity email & display_name.
    contacts_resp = notif_client.post(
        "/api/v1/internal/users/notification-contacts",
        {"user_ids": [str(member.pk), str(leader.pk)]},
        format="json",
        **notif_headers,
    )
    assert contacts_resp.status_code == 200, contacts_resp.content
    contacts_by_id = {row["user_id"]: row for row in contacts_resp.json()["users"]}
    assert contacts_by_id[str(member.pk)]["email"] == member.email
    assert contacts_by_id[str(member.pk)]["display_name"] == "Truong Phat"
    assert contacts_by_id[str(member.pk)]["account_status"] == AccountStatus.ACTIVE
    assert contacts_by_id[str(leader.pk)]["email"] == leader.email


def test_logout_session_revocation_immediately_blocks_classroom_and_work_apis(
    db, monkeypatch: pytest.MonkeyPatch
):
    student = _create_verified_user(
        first_name="Tuan",
        last_name="Ngo",
        role="STUDENT",
        student_id=f"SV{uuid4().hex[:6].upper()}",
    )
    client = _login_as(student)

    # Active session works on both Classroom and Work APIs.
    assert client.get("/api/classroom/courses/").status_code == 200
    assert client.get("/api/work/projects/").status_code == 200

    # Logout revokes UserSession in PostgreSQL.
    logout_resp = client.post("/api/auth/logout", {}, format="json")
    assert logout_resp.status_code == 200, logout_resp.content
    assert not UserSession.objects.filter(
        user=student, is_revoked=False, expires_at__gt=timezone.now()
    ).exists()

    # Forbid any outbound HTTP call to prove revocation check is strictly in-process PostgreSQL.
    def _no_network(*args, **kwargs):
        raise AssertionError("Unexpected outbound HTTP call during JWT session revocation check")

    monkeypatch.setattr("requests.request", _no_network)
    monkeypatch.setattr("requests.get", _no_network)
    monkeypatch.setattr("requests.post", _no_network)

    # Reusing the same Bearer token immediately returns 401 TOKEN_REVOKED on Classroom & Work.
    classroom_after = client.get("/api/classroom/courses/")
    assert classroom_after.status_code == 401
    assert classroom_after.json()["error"]["code"] == "TOKEN_REVOKED"

    work_after = client.get("/api/work/projects/")
    assert work_after.status_code == 401
    assert work_after.json()["error"]["code"] == "TOKEN_REVOKED"
