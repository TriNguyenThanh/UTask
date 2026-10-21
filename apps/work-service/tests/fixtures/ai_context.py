"""Dữ liệu và caller cho provider context; Identity/Classroom vẫn là fixture."""

from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

from apps.projects.models import Project, State
from apps.sprints.models import Sprint
from apps.tasks.models import Task

AI_KEY = "ai-context-test-key-" + "a" * 32
INTEGRATION_KEY = "integration-context-test-key-" + "b" * 32


@pytest.fixture
def ai_keys(settings):
    settings.WORK_SERVICE_KEYS = {"ai": [AI_KEY], "integration": [INTEGRATION_KEY]}
    settings.INTEGRATION_WORK_SERVICE_KEYS = []
    settings.WORK_INTEGRATION_SERVICE_KEY = "outbound-distinct-" + "c" * 32
    return {"ai": AI_KEY, "integration": INTEGRATION_KEY}


@pytest.fixture
def context_client(ai_keys, actors, client_for):
    def build(role="member", caller="ai"):
        client = client_for(actors[role])
        client.defaults["HTTP_X_SERVICE_KEY"] = ai_keys[caller]
        return client

    return build


@pytest.fixture
def context_targets(created_project, task_api):
    _, _, create = task_api
    task = create(story_points=5)
    sprint = Sprint.objects.create(project_id=created_project["id"], name="Chu kỳ test")
    return {"project": created_project["id"], "task": task["id"], "sprint": str(sprint.pk)}


@pytest.fixture
def context_schema():
    root = Path(__file__).resolve().parents[4]
    specification = yaml.safe_load(
        (root / "contracts/api/work-ai-context-v1.yaml").read_text("utf-8")
    )
    schema = {
        "$ref": "#/components/schemas/ContextDocument",
        "components": specification["components"],
    }
    return Draft202012Validator(schema, format_checker=FormatChecker())


@pytest.fixture
def context_task_factory(created_project, actors):
    project = Project.objects.get(pk=created_project["id"])
    state = State.objects.get(project=project, is_default=True)

    def create(count=1, **changes):
        start = (
            Task.objects.filter(project=project)
            .order_by("-sequence_id")
            .values_list("sequence_id", flat=True)
            .first()
            or 0
        ) + 1
        rows = [
            Task(
                project=project,
                state=state,
                sequence_id=start + index,
                created_by_user_id=actors["leader"],
                **{"title": f"Công việc {start + index}", **changes},
            )
            for index in range(count)
        ]
        Task.objects.bulk_create(rows)
        return rows

    return create


def context_url(target_type, target_id, domain=None):
    base = f"/api/v1/internal/ai/targets/{target_type}/{target_id}"
    return base + (f"/contexts/{domain}" if domain else "/authorize")
