import pytest
from drf_spectacular.generators import SchemaGenerator

from tests.fixtures.classroom import GroupMemberFact, GroupSnapshot
from tests.fixtures.sprints import draft


@pytest.fixture(scope="module")
def response_schema():
    return SchemaGenerator().get_schema(request=None, public=True)


@pytest.fixture
def read_routes(github):
    _, leader, repository, task = github
    sprint = draft(leader, task.project_id, "Read scope")
    return {
        "sprint_list": f"/api/v1/projects/{task.project_id}/sprints/",
        "sprint_detail": f"/api/v1/sprints/{sprint['id']}/",
        "repository": repository,
        "github_links": f"/api/v1/tasks/{task.pk}/github-links/",
    }


@pytest.fixture
def foreign_scope(classroom, actors, client_for):
    snapshot = GroupSnapshot(
        "other-group",
        "other-class",
        1,
        (
            GroupMemberFact(actors["leader"], "LEADER"),
            GroupMemberFact(actors["outsider"], "MEMBER"),
        ),
    )
    classroom.groups[snapshot.group_id] = snapshot
    leader = client_for(actors["leader"])
    reply = leader.post(
        "/api/v1/projects/",
        {"identifier": "OTHER", "name": "Other scope", "classroom_group_id": snapshot.group_id},
        format="json",
        HTTP_IDEMPOTENCY_KEY="other-project",
    )
    assert reply.status_code == 201, reply.content
    project = reply.json()["data"]
    task = leader.post(
        f"/api/v1/projects/{project['id']}/tasks/",
        {"title": "Foreign task", "assignee_ids": [str(actors["outsider"])]},
        format="json",
        HTTP_IDEMPOTENCY_KEY="foreign-task",
    )
    assert task.status_code == 201, task.content
    return project, task.json()["data"]
