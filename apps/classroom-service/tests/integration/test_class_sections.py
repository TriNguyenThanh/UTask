from datetime import timedelta
from uuid import uuid4

import pytest
from django.db import connection
from django.utils import timezone

from apps.courses.models import ClassTeacher, Enrollment
from apps.courses.services.classes import change_class, create_class, issue_class_code
from common.errors import ClassroomError
from infrastructure.identity import IdentityClient

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize("class_exists", [True, False])
@pytest.mark.parametrize("actor", ["external", "enrolled"])
@pytest.mark.parametrize("dependency", ["invalid_teacher", "unavailable"])
def test_unassigned_actor_cannot_probe_teacher_profiles_or_call_identity(
    section, actors, client_for, post_command, monkeypatch, class_exists, actor, dependency
):
    calls = []
    target = uuid4()

    def users(*args):
        calls.append("users")
        if dependency == "unavailable":
            raise ClassroomError("IDENTITY_UNAVAILABLE", "Không thể xác minh tài khoản.", 503)
        return [{"id": str(target), "roles": ["STUDENT"], "account_status": "ACTIVE"}]

    monkeypatch.setattr(IdentityClient, "users", users)
    actor_id = uuid4() if actor == "external" else actors["member"]
    class_id = section.pk if class_exists else uuid4()
    response = post_command(
        client_for(actor_id),
        f"/classes/{class_id}/teachers/assign/",
        {"version": 1, "user_id": str(target), "role": "CO_TEACHER", "status": "ACTIVE"},
    )
    assert response.status_code == (403 if class_exists and actor == "enrolled" else 404)
    assert calls == []
    assert not ClassTeacher.objects.filter(user_id=target).exists()
    section.refresh_from_db()
    assert section.version == 1


@pytest.mark.parametrize("retains_read", [True, False])
def test_teacher_assignment_revoked_during_identity_lookup_is_rechecked_before_commit(
    section, actors, command_request, monkeypatch, retains_read
):
    target = uuid4()
    if retains_read:
        Enrollment.objects.create(class_section=section, user_id=actors["teacher"])

    def users(*args):
        assert not connection.in_atomic_block
        ClassTeacher.objects.filter(class_section=section, user_id=actors["teacher"]).update(
            status="LEFT", left_at=timezone.now()
        )
        return [{"id": str(target), "roles": ["TEACHER"], "account_status": "ACTIVE"}]

    monkeypatch.setattr(IdentityClient, "users", users)
    with pytest.raises(ClassroomError) as error:
        change_class(
            command_request(actors["teacher"], "/teacher/", roles=("TEACHER",)),
            section.pk,
            {"version": 1, "user_id": target, "role": "CO_TEACHER", "status": "ACTIVE"},
            action="teacher",
        )
    assert error.value.status_code == (403 if retains_read else 404)
    assert not ClassTeacher.objects.filter(user_id=target).exists()
    section.refresh_from_db()
    assert section.version == 1


@pytest.mark.parametrize("roles", [["TEACHER"], "NOT_TEACHER", "TEACHER", None])
def test_teacher_assignment_requires_typed_identity_role_before_writing(
    section, actors, command_request, monkeypatch, roles
):
    target = uuid4()

    class IdentityReply:
        status_code = 200

        def json(self):
            return {
                "success": True,
                "data": {
                    "users": [{"id": str(target), "roles": roles, "account_status": "ACTIVE"}]
                },
            }

    monkeypatch.setattr("infrastructure.identity.requests.request", lambda *a, **k: IdentityReply())
    request = command_request(actors["teacher"], "/teacher/", roles=("TEACHER",))
    payload = {"version": 1, "user_id": target, "role": "CO_TEACHER", "status": "ACTIVE"}
    if isinstance(roles, list):
        assert change_class(request, section.pk, payload, action="teacher").status_code == 200
        assert ClassTeacher.objects.get(user_id=target).status == "ACTIVE"
    else:
        with pytest.raises(ClassroomError) as error:
            change_class(request, section.pk, payload, action="teacher")
        assert error.value.code == "IDENTITY_UNAVAILABLE"
        assert not ClassTeacher.objects.filter(user_id=target).exists()
        section.refresh_from_db()
        assert section.version == 1


def test_class_update_capacity_stale_state_and_last_teacher(group, actors, command_request):
    section = group.class_section

    def teacher(path="/class/"):
        return command_request(actors["teacher"], path, roles=("TEACHER",))

    updated = change_class(teacher(), section.pk, {"version": 1, "name": "Lớp đã sửa"})
    assert updated.data["data"]["name"] == "Lớp đã sửa"
    with pytest.raises(ClassroomError) as stale:
        change_class(teacher(), section.pk, {"version": 1, "name": "Cũ"})
    assert stale.value.code == "VERSION_CONFLICT"
    with pytest.raises(ClassroomError) as capacity:
        change_class(teacher(), section.pk, {"version": 2, "group_max_size": 1})
    assert capacity.value.code == "GROUP_CAPACITY_CONFLICT"
    with pytest.raises(ClassroomError) as last:
        change_class(
            teacher(),
            section.pk,
            {"version": 2, "user_id": actors["teacher"], "status": "LEFT", "role": "PRIMARY"},
            action="teacher",
        )
    assert last.value.code == "LAST_TEACHER_REQUIRED"
    response = change_class(
        teacher(), section.pk, {"version": 2, "status": "ARCHIVED"}, action="state"
    )
    assert response.data["data"]["status"] == "ARCHIVED"
    with pytest.raises(ClassroomError) as archived:
        change_class(teacher(), section.pk, {"version": 3, "status": "OPEN"}, action="state")
    assert archived.value.code == "CLASS_ARCHIVED"


def test_teacher_target_must_be_active_teacher(section, actors, identity, command_request):
    target = uuid4()
    identity["profiles"][str(target)] = {
        "id": str(target),
        "roles": ["TEACHER"],
        "account_status": "SUSPENDED",
    }
    with pytest.raises(ClassroomError) as invalid:
        change_class(
            command_request(actors["teacher"], "/teacher/", roles=("TEACHER",)),
            section.pk,
            {"version": 1, "user_id": target, "role": "CO_TEACHER", "status": "ACTIVE"},
            action="teacher",
        )
    assert invalid.value.code == "INVALID_TEACHER"
    assert not ClassTeacher.objects.filter(user_id=target).exists()


def test_teacher_creation_assigns_self_and_cannot_create_for_another_teacher(
    section, actors, command_request
):
    from apps.courses.services.classes import create_class

    request = command_request(actors["teacher"], "/classes/", roles=("TEACHER",))
    payload = {
        "course_id": section.course_id,
        "primary_teacher_id": uuid4(),
        "code": "SE02",
        "name": "Lớp mới",
        "term": "2026",
        "starts_on": section.starts_on,
        "ends_on": section.ends_on,
    }
    with pytest.raises(ClassroomError) as error:
        create_class(request, payload)
    assert error.value.status_code == 403


def test_code_disable_and_past_expiry_are_explicit(section, actors, command_request):
    def teacher():
        return command_request(actors["teacher"], "/code/", roles=("TEACHER",))

    with pytest.raises(ClassroomError):
        issue_class_code(
            teacher(),
            section.pk,
            {"version": 1, "enabled": True, "expires_at": timezone.now() - timedelta(seconds=1)},
        )
    response = issue_class_code(teacher(), section.pk, {"version": 1, "enabled": False})
    assert response.data["data"]["enabled"] is False and "code" not in response.data["data"]
    assert "tắt mã" in response.data["message"]


def test_students_only_see_current_teachers_of_their_class(section, actors, client_for):
    old_teacher = uuid4()
    ClassTeacher.objects.create(
        class_section=section, user_id=old_teacher, status="LEFT", left_at=timezone.now()
    )
    path = f"/classes/{section.pk}/teachers/"
    student = client_for(actors["member"])
    response = student.get(path)
    assert response.status_code == 200
    assert [row["user_id"] for row in response.json()["data"]] == [str(actors["teacher"])]
    assert student.get(path, {"status": "LEFT"}).json()["data"] == []
    assert len(client_for(actors["teacher"]).get(path).json()["data"]) == 2
    Enrollment.objects.filter(class_section=section, user_id=actors["member"]).update(
        status="LEFT", left_at=timezone.now()
    )
    assert student.get(path).status_code == 404


def test_teacher_list_pagination_and_scope(group, actors, client_for):
    section = group.class_section
    ClassTeacher.objects.create(class_section=section, user_id=uuid4())
    response = client_for(actors["teacher"]).get(f"/classes/{section.pk}/teachers/?page_size=1")
    assert response.status_code == 200 and len(response.json()["data"]) == 1
    assert response.json()["meta"]["pagination"]["next_cursor"]
    assert client_for(actors["leader"]).get(f"/classes/{section.pk}/teachers/").status_code == 200


def test_teacher_assignment_replay_does_not_reverify_target_status(
    section, actors, command_request, identity
):
    assigned = uuid4()
    identity["profiles"][str(assigned)] = {
        "id": str(assigned),
        "roles": ["TEACHER"],
        "account_status": "ACTIVE",
    }
    request = command_request(actors["teacher"], "/teacher/", roles=("TEACHER",))
    payload = {"version": 1, "user_id": assigned, "role": "CO_TEACHER", "status": "ACTIVE"}
    response = change_class(request, section.pk, payload, action="teacher")
    identity["profiles"][str(assigned)]["account_status"] = "SUSPENDED"
    assert change_class(request, section.pk, payload, action="teacher").data == response.data


def test_admin_class_create_replay_does_not_reverify_assigned_teacher(
    section, actors, command_request, identity
):
    assigned = actors["teacher"]
    identity["profiles"][str(assigned)] = {
        "id": str(assigned),
        "roles": ["TEACHER"],
        "account_status": "ACTIVE",
    }
    request = command_request(actors["admin"], "/classes/", roles=("SYSTEM_ADMIN",))
    payload = {
        "course_id": section.course_id,
        "primary_teacher_id": assigned,
        "code": "SE02",
        "name": "Lớp mới",
        "term": "2026",
        "starts_on": section.starts_on,
        "ends_on": section.ends_on,
        "group_min_size": 1,
        "group_max_size": 3,
    }
    response = create_class(request, payload)
    identity["profiles"][str(assigned)]["account_status"] = "SUSPENDED"
    assert create_class(request, payload).data == response.data
