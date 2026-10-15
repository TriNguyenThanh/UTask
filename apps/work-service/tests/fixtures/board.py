import pytest

from apps.projects.models import State
from apps.tasks.models import Task, TaskAssignment


@pytest.fixture
def board_tasks(created_project, actors):
    states = list(State.objects.filter(project_id=created_project["id"]).order_by("sequence"))
    tasks = []
    for i in range(1, 9):
        tasks.append(
            Task.objects.create(
                project_id=created_project["id"],
                state=states[i % 2],
                sequence_id=i,
                title=f"Card {i}",
                created_by_user_id=actors["leader"],
                sort_order=10000 * (i // 3),
                priority="HIGH" if i % 2 else "LOW",
            )
        )
    TaskAssignment.objects.create(task=tasks[0], user_id=actors["leader"])
    TaskAssignment.objects.create(task=tasks[0], user_id=actors["member"])
    return tasks
