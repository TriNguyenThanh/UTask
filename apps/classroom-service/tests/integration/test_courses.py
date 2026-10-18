from uuid import uuid4

import pytest

from apps.courses.models import Course
from apps.messaging.models import IdempotencyRecord

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize("actor_name", ["teacher", "admin"])
def test_course_admin_create_update_archive_and_student_denied(
    client_for, actors, post_command, actor_name
):
    client = client_for(actors[actor_name])
    payload = {"code": "cs", "name": "Tin học"}
    create_key = uuid4()
    response = post_command(client, "/courses/", payload, key=create_key)
    assert response.status_code == 201
    pk = response.json()["data"]["id"]
    assert Course.objects.get(pk=pk).name == "Tin học"
    assert Course.objects.get(pk=pk).created_by_id == actors[actor_name]
    assert response.json()["data"]["created_by_id"] == str(actors[actor_name])
    replay = post_command(client, "/courses/", payload, key=create_key)
    assert replay.status_code == 201 and replay.json() == response.json()
    assert Course.objects.count() == 1

    payload = {"code": "cs", "name": "Tin học cơ sở"}
    update_key = str(uuid4())
    update = client.patch(
        f"/courses/{pk}/",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY=update_key,
    )
    assert update.status_code == 200 and update.json()["data"]["name"] == "Tin học cơ sở"
    assert Course.objects.get(pk=pk).name == "Tin học cơ sở"
    replay = client.patch(
        f"/courses/{pk}/", payload, format="json", HTTP_IDEMPOTENCY_KEY=update_key
    )
    assert replay.status_code == 200 and replay.json() == update.json()

    archive_key = uuid4()
    archive = post_command(client, f"/courses/{pk}/archive/", {}, key=archive_key)
    assert archive.status_code == 200
    archived_at = Course.objects.get(pk=pk).archived_at
    assert archived_at is not None
    replay = post_command(client, f"/courses/{pk}/archive/", {}, key=archive_key)
    assert replay.status_code == 200 and replay.json() == archive.json()
    assert Course.objects.get(pk=pk).archived_at == archived_at
    assert IdempotencyRecord.objects.count() == 3
    assert (
        post_command(
            client_for(actors["leader"]), "/courses/", {"code": "S", "name": "Sai"}
        ).status_code
        == 403
    )
    listing = client_for(actors["leader"]).get("/courses/")
    assert listing.status_code == 200 and listing.json()["data"][0]["id"] == pk


@pytest.mark.parametrize("operation", ["create", "update", "archive"])
def test_student_cannot_mutate_courses_or_claim_receipt(
    client_for, actors, post_command, operation
):
    course = Course.objects.create(code="CS", name="Tin học")
    before = list(Course.objects.values())
    client = client_for(actors["leader"])
    if operation == "update":
        response = client.patch(
            f"/courses/{course.pk}/",
            {"code": "EDITED", "name": "Đã đổi"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
        )
    elif operation == "archive":
        response = post_command(client, f"/courses/{course.pk}/archive/", {})
    else:
        response = post_command(client, "/courses/", {"code": "NEW", "name": "Môn mới"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"
    assert list(Course.objects.values()) == before
    assert IdempotencyRecord.objects.count() == 0


@pytest.mark.parametrize("operation", ["create", "update", "archive"])
def test_teacher_losing_role_cannot_replay_course_command(
    client_for, actors, post_command, identity, operation
):
    client = client_for(actors["teacher"])
    payload = {"code": "CS", "name": "Tin học"}
    key = uuid4()
    created = post_command(client, "/courses/", payload, key=key)
    assert created.status_code == 201
    course_id = created.json()["data"]["id"]
    if operation == "update":
        key = uuid4()
        path = f"/courses/{course_id}/"
        assert (
            client.patch(path, payload, format="json", HTTP_IDEMPOTENCY_KEY=str(key)).status_code
            == 200
        )
    elif operation == "archive":
        key = uuid4()
        path = f"/courses/{course_id}/archive/"
        payload = {}
        assert post_command(client, path, payload, key=key).status_code == 200
    else:
        path = "/courses/"
    before = list(Course.objects.values())
    receipts_before = IdempotencyRecord.objects.count()
    identity["roles"][str(actors["teacher"])] = ["STUDENT"]

    response = (
        client.patch(path, payload, format="json", HTTP_IDEMPOTENCY_KEY=str(key))
        if operation == "update"
        else post_command(client, path, payload, key=key)
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"
    assert list(Course.objects.values()) == before
    assert IdempotencyRecord.objects.count() == receipts_before


@pytest.mark.parametrize("creator", ["other", "legacy"])
@pytest.mark.parametrize("operation", ["update", "archive"])
def test_teacher_cannot_mutate_other_or_legacy_course(
    client_for, actors, post_command, creator, operation
):
    course = Course.objects.create(
        code="CS", name="Tin học", created_by_id=actors["admin"] if creator == "other" else None
    )
    client = client_for(actors["teacher"])
    before = list(Course.objects.values())

    response = (
        client.patch(
            f"/courses/{course.pk}/",
            {"code": "NEW", "name": "Môn mới"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
        )
        if operation == "update"
        else post_command(client, f"/courses/{course.pk}/archive/", {})
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"
    assert list(Course.objects.values()) == before
    assert IdempotencyRecord.objects.count() == 0


@pytest.mark.parametrize("creator", ["teacher", "legacy"])
def test_admin_can_manage_courses_without_taking_ownership(
    client_for, actors, post_command, creator
):
    creator_id = actors["teacher"] if creator == "teacher" else None
    course = Course.objects.create(code="CS", name="Tin học", created_by_id=creator_id)
    client = client_for(actors["admin"])

    update = client.patch(
        f"/courses/{course.pk}/",
        {"code": "NEW", "name": "Môn mới"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid4()),
    )
    assert update.status_code == 200
    archive = post_command(client, f"/courses/{course.pk}/archive/", {})
    assert archive.status_code == 200
    course.refresh_from_db()
    assert course.created_by_id == creator_id
    assert course.archived_at is not None


@pytest.mark.parametrize("operation", ["update", "archive"])
def test_former_admin_cannot_replay_unowned_course_command(
    client_for, actors, post_command, identity, operation
):
    course = Course.objects.create(code="CS", name="Tin học", created_by_id=actors["teacher"])
    client = client_for(actors["admin"])
    key = uuid4()
    path = f"/courses/{course.pk}/" + ("archive/" if operation == "archive" else "")
    payload = {} if operation == "archive" else {"code": "CS", "name": "Môn mới"}
    if operation == "archive":
        initial = post_command(client, path, payload, key=key)
    else:
        initial = client.patch(path, payload, format="json", HTTP_IDEMPOTENCY_KEY=str(key))
    assert initial.status_code == 200
    before = list(Course.objects.values())
    identity["roles"][str(actors["admin"])] = ["TEACHER"]

    response = (
        post_command(client, path, payload, key=key)
        if operation == "archive"
        else client.patch(path, payload, format="json", HTTP_IDEMPOTENCY_KEY=str(key))
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"
    assert list(Course.objects.values()) == before
    assert IdempotencyRecord.objects.count() == 1


@pytest.mark.parametrize("actor_name", ["teacher", "admin", "leader"])
def test_authenticated_roles_can_list_course_creator(client_for, actors, actor_name):
    course = Course.objects.create(code="CS", name="Tin học", created_by_id=actors["teacher"])

    response = client_for(actors[actor_name]).get("/courses/")

    assert response.status_code == 200
    assert response.json()["data"][0]["id"] == str(course.pk)
    assert response.json()["data"][0]["created_by_id"] == str(actors["teacher"])


def test_unauthenticated_user_cannot_list_courses(client_for, actors):
    client = client_for(actors["leader"])
    client.credentials()

    assert client.get("/courses/").status_code == 401


def test_teacher_cannot_supply_course_creator(client_for, actors, post_command):
    response = post_command(
        client_for(actors["teacher"]),
        "/courses/",
        {"code": "CS", "name": "Tin học", "created_by_id": str(actors["admin"])},
    )

    assert response.status_code == 400
    assert Course.objects.count() == 0
    assert IdempotencyRecord.objects.count() == 0
