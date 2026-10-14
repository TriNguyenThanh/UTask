import pytest
from django.utils import timezone

from apps.sprints.models import Sprint
from tests.assertions.api_reads import read
from tests.fixtures.sprints import draft

pytestmark = [pytest.mark.integration, pytest.mark.contract, pytest.mark.django_db]


def test_sprint_list_pagination_status_filter_and_archived_rows(
    created_project, actors, client_for, response_schema
):
    leader = client_for(actors["leader"])
    listing = f"/api/v1/projects/{created_project['id']}/sprints/"
    drafts = [draft(leader, created_project["id"], str(i)) for i in range(3)]
    hidden = draft(leader, created_project["id"], "Archived")
    Sprint.objects.filter(pk=hidden["id"]).update(archived_at=timezone.now())
    first = read(leader, listing, response_schema, {"status": "DRAFT", "page_size": 2})
    pagination = first["meta"]["pagination"]
    assert pagination["total_count"] == 3 and pagination["has_next"]
    assert pagination["page_size"] == 2 and pagination["prev_cursor"] is None
    cursor = pagination["next_cursor"]
    second = read(
        leader, listing, response_schema, {"status": "DRAFT", "page_size": 2, "cursor": cursor}
    )
    ids = [x["id"] for x in first["data"] + second["data"]]
    assert len(ids) == len(set(ids)) == 3
    assert set(ids) == {x["id"] for x in drafts}
    assert not second["meta"]["pagination"]["has_next"]
    assert second["meta"]["pagination"]["next_cursor"] is None
    for params in (
        {"status": "UNKNOWN"},
        {"page_size": 0},
        {"status": "DRAFT", "cursor": cursor + "tampered"},
        {"status": "ACTIVE", "cursor": cursor},
    ):
        read(leader, listing, response_schema, params, status=400)
    read(client_for(actors["member"]), listing, response_schema, {"cursor": cursor}, status=400)
