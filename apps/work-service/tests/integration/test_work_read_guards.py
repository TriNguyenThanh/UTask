import pytest

from apps.sprints.models import Sprint
from tests.fixtures.transactions import effect_state

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.mark.parametrize(
    "resource,params",
    [
        ("projects", {"status": "invalid"}),
        ("members", {"status": "invalid"}),
        ("dashboard", {"unsupported": "value"}),
        ("tasks", {"unsupported": "value"}),
        ("tasks", {"status": "invalid"}),
        ("tasks", {"expand": "subtasks"}),
        ("board", {"priority": "invalid"}),
        ("board", {"cursor": "wrong-route"}),
    ],
)
def test_read_validation_errors_leave_all_project_effects_unchanged(task_api, resource, params):
    leader, task_route, create = task_api
    task = create()
    root = f"/api/v1/projects/{task['project_id']}/"
    path = (
        "/api/v1/projects/"
        if resource == "projects"
        else task_route
        if resource == "tasks"
        else root + {"members": "members/", "dashboard": "dashboard/", "board": "kanban/"}[resource]
    )
    before = effect_state(task["project_id"])
    reply = leader.get(path, params)
    assert reply.status_code == 400 and reply.json()["error"]["code"] == "VALIDATION_ERROR", (
        reply.content
    )
    assert effect_state(task["project_id"]) == before


@pytest.mark.parametrize("status", ["deleted", "all"])
def test_task_list_status_reads_back_soft_deleted_record_without_writes(task_api, status):
    leader, route, create = task_api
    live = create()
    deleted = create()
    archived = create()
    assert (
        leader.post(
            f"/api/v1/tasks/{archived['id']}/archive/", {"expected_version": 1}, format="json"
        ).status_code
        == 200
    )
    assert (
        leader.delete(
            f"/api/v1/tasks/{deleted['id']}/", {"expected_version": 1}, format="json"
        ).status_code
        == 200
    )
    before = effect_state(live["project_id"])
    reply = leader.get(route, {"status": status})
    assert reply.status_code == 200, reply.content
    assert {r["id"] for r in reply.json()["data"]} == (
        {deleted["id"]} if status == "deleted" else {live["id"], archived["id"]}
    )
    assert effect_state(live["project_id"]) == before


@pytest.mark.parametrize("surface", ["tasks", "board"])
@pytest.mark.parametrize("filter_value", ["none", "selected"])
def test_sprint_filter_uses_membership_without_duplicate_rows(task_api, surface, filter_value):
    leader, route, create = task_api
    assigned = create()
    backlog = create()
    sprint = Sprint.objects.create(project_id=assigned["project_id"], name="Filter")
    scope = leader.post(
        f"/api/v1/sprints/{sprint.pk}/tasks/",
        {"expected_version": 1, "action": "ADD", "task_ids": [assigned["id"]]},
        format="json",
        HTTP_IDEMPOTENCY_KEY="filter-scope",
    )
    assert scope.status_code == 200, scope.content
    path = route if surface == "tasks" else f"/api/v1/projects/{assigned['project_id']}/kanban/"
    reply = leader.get(path, {"sprint_id": "none" if filter_value == "none" else str(sprint.pk)})
    assert reply.status_code == 200, reply.content
    data = reply.json()["data"]
    rows = (
        data if surface == "tasks" else [task for col in data["columns"] for task in col["tasks"]]
    )
    assert {task["id"] for task in rows} == {
        backlog["id"] if filter_value == "none" else assigned["id"]
    }
    assert len(rows) == 1


@pytest.mark.parametrize("group_id,expected", [("group-1", 200), ("other-group", 403)])
def test_teacher_project_list_requires_selected_group_scope(
    created_project, actors, client_for, group_id, expected
):
    before = effect_state(created_project["id"])
    reply = client_for(actors["teacher"]).get(
        "/api/v1/projects/", {"classroom_group_id": group_id, "status": "all"}
    )
    assert reply.status_code == expected, reply.content
    if expected == 200:
        assert [row["id"] for row in reply.json()["data"]] == [created_project["id"]]
    assert effect_state(created_project["id"]) == before


def test_task_text_search_does_not_require_issue_code_shape(task_api):
    leader, route, create = task_api
    matched = create(title="Unique needle")
    create(title="Different")
    reply = leader.get(route, {"search": "Unique needle"})
    assert reply.status_code == 200 and [row["id"] for row in reply.json()["data"]] == [
        matched["id"]
    ]


@pytest.mark.parametrize("value", [True, False])
def test_block_explicit_flag_cannot_be_used_to_unblock(task_api, value):
    leader, _, create = task_api
    task = create()
    before = effect_state(task["project_id"])
    reply = leader.patch(
        f"/api/v1/tasks/{task['id']}/block/",
        {"expected_version": 1, "blocked_reason": "Waiting", "is_blocked": value},
        format="json",
    )
    assert reply.status_code == (200 if value else 400), reply.content
    if value:
        assert reply.json()["data"]["is_blocked"] is True
    else:
        assert effect_state(task["project_id"]) == before
