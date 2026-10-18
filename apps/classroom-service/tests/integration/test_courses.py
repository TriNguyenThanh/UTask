from uuid import uuid4

import pytest

from apps.courses.models import Course

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


def test_course_admin_create_update_archive_and_student_denied(client_for, actors, post_command):
    client = client_for(actors["admin"])
    response = post_command(client, "/courses/", {"code": "cs", "name": "Tin học"})
    assert response.status_code == 201
    pk = response.json()["data"]["id"]
    update = client.patch(
        f"/courses/{pk}/",
        {"code": "cs", "name": "Tin học cơ sở"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid4()),
    )
    assert update.status_code == 200 and update.json()["data"]["name"] == "Tin học cơ sở"
    assert post_command(client, f"/courses/{pk}/archive/", {}).status_code == 200
    assert Course.objects.get(pk=pk).archived_at
    assert (
        post_command(
            client_for(actors["leader"]), "/courses/", {"code": "S", "name": "Sai"}
        ).status_code
        == 403
    )
    listing = client_for(actors["leader"]).get("/courses/")
    assert listing.status_code == 200 and listing.json()["data"][0]["id"] == pk
