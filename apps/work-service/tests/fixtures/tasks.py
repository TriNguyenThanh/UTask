import pytest

from apps.tasks.models import Task, TaskLabel
from tests.fixtures.transactions import effect_state


@pytest.fixture
def task_labels(task_api):
    leader, route, create = task_api
    task = create()
    root = f"/projects/{task['project_id']}/labels/"
    labels = []
    for name in ["Backend", "Reviewed"]:
        reply = leader.post(root, {"name": name, "color": "#123456"}, format="json")
        assert reply.status_code == 201, reply.content
        labels.append(reply.json()["data"]["id"])
    return leader, f"/tasks/{task['id']}/labels/", task, labels


def label_state(task):
    return {
        "effects": effect_state(task["project_id"]),
        "task": Task.objects.filter(pk=task["id"]).values().get(),
        "junctions": list(
            TaskLabel.objects.filter(task_id=task["id"]).order_by("label_id").values()
        ),
    }
