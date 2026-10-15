import re
from uuid import uuid4

import pytest
import requests
from django.utils import timezone
from rest_framework.test import APIClient

from apps.projects.models import ProjectMember
from tests.assertions.api_reads import read

pytestmark = [pytest.mark.integration, pytest.mark.contract, pytest.mark.django_db]


@pytest.mark.parametrize("endpoint", ["sprint_list", "sprint_detail", "repository", "github_links"])
def test_read_scope_and_session_are_checked_on_every_request(
    endpoint, read_routes, actors, client_for, classroom, identity, response_schema, monkeypatch
):
    route = read_routes[endpoint]
    member = client_for(actors["member"])
    teacher = client_for(actors["teacher"])
    read(member, route, response_schema)
    read(teacher, route, response_schema)
    read(client_for(actors["outsider"]), route, response_schema, status=404)
    read(APIClient(), route, response_schema, status=401)
    identity["active"] = False
    read(member, route, response_schema, status=401)
    identity["active"] = True
    ProjectMember.objects.filter(user_id=actors["member"]).update(
        status="REMOVED", left_at=timezone.now()
    )
    read(member, route, response_schema, status=404)
    classroom.teachers[actors["teacher"]] = []
    read(teacher, route, response_schema, status=404)

    def unavailable(*args, **kwargs):
        raise requests.Timeout("provider-secret")

    monkeypatch.setattr("infrastructure.identity.requests.post", unavailable)
    error = read(member, route, response_schema, status=503)
    assert error["error"]["code"] == "IDENTITY_UNAVAILABLE"
    assert "provider-secret" not in str(error)


@pytest.mark.parametrize("endpoint", ["sprint_list", "sprint_detail", "repository", "github_links"])
def test_read_nonexistent_ids_do_not_leak_or_mutate(
    endpoint, read_routes, actors, client_for, response_schema
):
    route = re.sub(
        r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", str(uuid4()), read_routes[endpoint]
    )
    read(client_for(actors["leader"]), route, response_schema, status=404)
