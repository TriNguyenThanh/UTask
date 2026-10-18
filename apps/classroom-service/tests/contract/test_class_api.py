from uuid import uuid4

import pytest

from apps.courses.models import ClassSection, ClassTeacher
from apps.messaging.models import Activity, IdempotencyRecord

pytestmark = [pytest.mark.django_db, pytest.mark.contract]


def test_class_creation_replay_returns_original_class(
    class_creation_payload, client_for, actors, post_command
):
    teacher = client_for(actors["teacher"])
    key = uuid4()
    response = post_command(teacher, "/classes/", class_creation_payload, key)
    assert response.status_code == 201, response.content
    data = response.json()["data"]
    assert data["code"] == "SE02" and "join_code_hash" not in data
    assert ClassTeacher.objects.filter(
        class_section_id=data["id"], user_id=actors["teacher"], role="PRIMARY"
    ).exists()
    assert post_command(teacher, "/classes/", class_creation_payload, key).json() == response.json()
    assert ClassSection.objects.filter(code="SE02").count() == 1


def test_class_creation_rejects_changed_payload_for_same_key(
    class_creation_payload, client_for, actors, post_command
):
    teacher = client_for(actors["teacher"])
    key = uuid4()
    assert post_command(teacher, "/classes/", class_creation_payload, key).status_code == 201
    conflict = post_command(teacher, "/classes/", {**class_creation_payload, "name": "Khác"}, key)
    assert conflict.status_code == 422
    assert ClassSection.objects.get(code="SE02").name == class_creation_payload["name"]


def test_class_creation_rejects_invalid_date_range(
    class_creation_payload, client_for, actors, post_command
):
    response = post_command(
        client_for(actors["teacher"]),
        "/classes/",
        {**class_creation_payload, "starts_on": "2027-01-01"},
    )
    assert response.status_code == 400 and response.json()["error"]["details"]
    assert not ClassSection.objects.filter(code="SE02").exists()


def test_student_cannot_create_class(class_creation_payload, client_for, actors, post_command):
    response = post_command(client_for(actors["leader"]), "/classes/", class_creation_payload)
    assert response.status_code == 403
    assert not ClassSection.objects.filter(code="SE02").exists()


def test_unrelated_user_cannot_read_class(section, client_for):
    assert client_for(uuid4()).get(f"/classes/{section.pk}/").status_code == 404


def test_class_code_replay_hides_secret_and_rotation_rejects_previous_code(
    section, client_for, actors, post_command
):
    route = f"/classes/{section.pk}/join-code/"
    teacher = client_for(actors["teacher"])
    key = uuid4()
    reply = post_command(teacher, route, {"version": 1}, key)
    assert reply.status_code == 200, reply.content
    code = reply.json()["data"]["code"]
    section.refresh_from_db()
    assert len(section.join_code_hash) == 64 and section.join_code_hash != code
    assert code not in str(list(Activity.objects.values()))
    assert code not in str(list(IdempotencyRecord.objects.values("response_body")))
    replay = post_command(teacher, route, {"version": 1}, key)
    assert replay.status_code == 200 and "code" not in replay.json()["data"]
    newcomer = client_for(uuid4())
    joined = post_command(newcomer, "/classes/join/", {"code": code.lower()})
    assert joined.status_code == 201, joined.content
    assert post_command(newcomer, "/classes/join/", {"code": code}).status_code == 200
    assert post_command(teacher, route, {"version": section.version}).status_code == 200
    assert post_command(client_for(uuid4()), "/classes/join/", {"code": code}).status_code == 404
