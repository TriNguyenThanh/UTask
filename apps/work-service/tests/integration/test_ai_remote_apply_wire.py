import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Barrier, Thread
from uuid import UUID

import pytest
from django.db import close_old_connections
from django.utils import timezone

from apps.messaging.models import IdempotencyRecord, OutboxEvent
from apps.projects.models import Project
from apps.tasks.models import Task, TaskRelation
from tests.fixtures.ai_proposals import action_payload, backlog_payload, sprint_action

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]

SERVICE_KEY = "k" * 32


@pytest.fixture
def ai_http_stub(settings):
    state = {
        "status": 200,
        "calls": [],
        "response_builder": None,
    }

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            body = json.loads(raw.decode("utf-8"))
            call = {
                "path": self.path,
                "service_key": self.headers.get("X-Service-Key"),
                "authorization": self.headers.get("Authorization"),
                "body": body,
            }
            state["calls"].append(call)
            status = state["status"]
            if callable(state["response_builder"]):
                status, payload = state["response_builder"](call)
            elif status == 200:
                payload = {}
            else:
                payload = {"detail": "Stub error"}
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    settings.WORK_AI_ADAPTER = "infrastructure.ai.RemoteProposals"
    settings.WORK_AI_BASE_URL = f"http://127.0.0.1:{port}"
    settings.WORK_AI_SERVICE_KEY = SERVICE_KEY
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_remote_ai_backlog_apply_over_real_http_and_replay_does_not_recall_ai(
    task_api, actors, ai_http_stub
):
    leader, route, _ = task_api
    project = Project.objects.get(pk=route.split("/")[2])

    def build_reply(call):
        return (
            200,
            {
                "proposal_id": "proposal-1",
                "proposal_type": "BACKLOG",
                "project_id": str(project.pk),
                "parent_task_id": None,
                "context_version": 42,
                "item_revisions": {"a": "r1", "b": "r1"},
                "actor_ids": [str(actors["leader"])],
                "expires_at": (timezone.now() + timedelta(hours=1)).isoformat(),
            },
        )

    ai_http_stub["response_builder"] = build_reply
    body = backlog_payload(project)
    apply_route = route + "bulk-apply-ai/"

    first = leader.post(apply_route, body, format="json", HTTP_IDEMPOTENCY_KEY="wire-backlog-1")
    assert first.status_code == 201, first.content
    assert first.json()["data"]["created_count"] == 2
    assert Task.objects.filter(project=project, source="AI_BACKLOG").count() == 2
    assert TaskRelation.objects.filter(relation_type="BLOCKS").count() == 1
    assert len(ai_http_stub["calls"]) == 1
    call = ai_http_stub["calls"][0]
    assert call["path"] == "/api/ai/v1/internal/requests/proposal-1/verify-proposal"
    assert call["service_key"] == SERVICE_KEY
    assert call["authorization"].startswith("Bearer ")
    assert call["body"] == {
        "proposal_type": "BACKLOG",
        "project_id": str(project.pk),
        "parent_task_id": None,
    }

    replay = leader.post(apply_route, body, format="json", HTTP_IDEMPOTENCY_KEY="wire-backlog-1")
    assert replay.status_code == 201
    assert replay.json() == first.json()
    assert len(ai_http_stub["calls"]) == 1


def test_remote_ai_subtask_apply_over_real_http_for_assigned_member(
    task_api, actors, client_for, ai_http_stub
):
    _, _, create = task_api
    parent = create(due_date="2027-01-01")
    member = client_for(actors["member"])

    ai_http_stub["response_builder"] = lambda call: (
        200,
        {
            "proposal_id": "subtask-prop-1",
            "proposal_type": "SUBTASK",
            "project_id": parent["project_id"],
            "parent_task_id": parent["id"],
            "context_version": "42",
            "item_revisions": {"sub-1": "rev-a"},
            "actor_ids": [str(actors["member"])],
            "expires_at": (timezone.now() + timedelta(hours=1)).isoformat(),
        },
    )
    subroute = f"/tasks/{parent['id']}/subtasks/bulk-apply-ai/"
    payload = {
        "proposal_id": "subtask-prop-1",
        "context_version": 42,
        "expected_parent_version": parent["version"],
        "subtasks": [
            {
                "local_id": "sub-1",
                "ai_revision": "rev-a",
                "title": "Viết kiểm thử tích hợp",
                "acceptance_criteria": "Tất cả kiểm thử đạt",
            }
        ],
    }

    denied = {**payload, "subtasks": [{**payload["subtasks"][0], "story_points": 5}]}
    forbidden = member.post(subroute, denied, format="json", HTTP_IDEMPOTENCY_KEY="wire-sub-denied")
    assert forbidden.status_code == 403
    assert len(ai_http_stub["calls"]) == 0

    reply = member.post(subroute, payload, format="json", HTTP_IDEMPOTENCY_KEY="wire-sub-1")
    assert reply.status_code == 201, reply.content
    assert len(ai_http_stub["calls"]) == 1
    assert ai_http_stub["calls"][0]["body"] == {
        "proposal_type": "SUBTASK",
        "project_id": parent["project_id"],
        "parent_task_id": parent["id"],
    }
    child = Task.objects.get(ai_local_id="sub-1")
    assert child.source == "AI_DECOMPOSED"
    assert child.parent_id == UUID(parent["id"])


@pytest.mark.parametrize(
    ("scenario", "expected_status", "expected_code"),
    [
        ("http_410", 410, "AI_PROPOSAL_EXPIRED"),
        ("http_404", 404, "AI_PROPOSAL_NOT_FOUND"),
        ("http_403", 403, "AI_PROVENANCE_INVALID"),
        ("http_409", 409, "AI_PROVENANCE_INVALID"),
        ("http_500", 503, "AI_DEPENDENCY_UNAVAILABLE"),
        ("tampered_revision", 422, "AI_PROVENANCE_INVALID"),
        ("stale_context", 422, "AI_PROVENANCE_INVALID"),
        ("unreachable", 503, "AI_DEPENDENCY_UNAVAILABLE"),
    ],
)
def test_remote_ai_http_error_and_tamper_propagation(
    task_api, actors, ai_http_stub, settings, scenario, expected_status, expected_code
):
    leader, route, _ = task_api
    project = Project.objects.get(pk=route.split("/")[2])
    body = backlog_payload(project)

    if scenario.startswith("http_"):
        ai_http_stub["status"] = int(scenario.split("_")[1])
    elif scenario == "unreachable":
        settings.WORK_AI_BASE_URL = "http://127.0.0.1:1"
    else:
        ai_http_stub["response_builder"] = lambda call: (
            200,
            {
                "proposal_id": "proposal-1",
                "proposal_type": "BACKLOG",
                "project_id": str(project.pk),
                "parent_task_id": None,
                "context_version": 99 if scenario == "stale_context" else 42,
                "item_revisions": {
                    "a": "tampered" if scenario == "tampered_revision" else "r1",
                    "b": "r1",
                },
                "actor_ids": [str(actors["leader"])],
                "expires_at": (timezone.now() + timedelta(hours=1)).isoformat(),
            },
        )

    reply = leader.post(
        route + "bulk-apply-ai/",
        body,
        format="json",
        HTTP_IDEMPOTENCY_KEY=f"wire-err-{scenario}",
    )
    assert reply.status_code == expected_status, reply.content
    assert reply.json()["error"]["code"] == expected_code
    assert any("À" <= char <= "ỹ" for char in reply.json()["message"])
    if scenario != "unreachable":
        assert len(ai_http_stub["calls"]) == 1
    assert not Task.objects.exists()
    assert not IdempotencyRecord.objects.filter(idempotency_key=f"wire-err-{scenario}").exists()


def test_remote_ai_action_apply_rejected_cleanly_in_v1(task_api, ai_http_stub):
    leader, route, create = task_api
    project_id = route.split("/")[2]
    task = create()
    sprint = leader.post(
        f"/projects/{project_id}/sprints/",
        {"name": "Sprint 1"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="sprint-1",
    )
    assert sprint.status_code == 201
    sprint_data = sprint.json()["data"]
    payload = action_payload(sprint_action(task, sprint_data, sprint_data["version"]))

    reply = leader.post(
        f"/projects/{project_id}/ai-actions/apply/",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="wire-action-v1",
    )
    assert reply.status_code == 422, reply.content
    assert reply.json()["error"]["code"] == "AI_PROVENANCE_INVALID"
    assert len(ai_http_stub["calls"]) == 0


@pytest.mark.postgres
def test_remote_ai_concurrent_two_keys_create_items_once_on_postgres(
    task_api, actors, client_for, ai_http_stub
):
    _, route, _ = task_api
    project = Project.objects.get(pk=route.split("/")[2])
    ai_http_stub["response_builder"] = lambda call: (
        200,
        {
            "proposal_id": "proposal-1",
            "proposal_type": "BACKLOG",
            "project_id": str(project.pk),
            "parent_task_id": None,
            "context_version": 42,
            "item_revisions": {"a": "r1", "b": "r1"},
            "actor_ids": [str(actors["leader"])],
            "expires_at": (timezone.now() + timedelta(hours=1)).isoformat(),
        },
    )
    body = backlog_payload(project)
    barrier = Barrier(2)

    def send(index):
        close_old_connections()
        try:
            client = client_for(actors["leader"])
            barrier.wait(timeout=10)
            response = client.post(
                route + "bulk-apply-ai/",
                body,
                format="json",
                HTTP_IDEMPOTENCY_KEY=f"wire-race-{index}",
            )
            assert response.status_code == 201, response.content
            return response.json()["data"]
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(send, [1, 2]))
    assert sorted(result["created_count"] for result in results) == [0, 2]
    assert Task.objects.count() == 2
    assert Project.objects.get(pk=project.pk).current_task_sequence == 2
    assert OutboxEvent.objects.filter(event_type="work.ai_proposal.applied").count() == 1
