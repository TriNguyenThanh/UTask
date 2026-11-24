import json
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Barrier, Thread
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
import yaml
from django.core.cache import cache
from django.db import close_old_connections
from jsonschema import Draft202012Validator

from apps.integrations.models import GitHubConnectionOperation, TaskGitHubLink
from apps.messaging.integration_consumer import process_connection_record
from apps.messaging.models import ConsumedEvent, OutboxEvent
from apps.projects.models import Project, ProjectMember
from tests.fixtures.classroom import GroupMemberFact, GroupSnapshot

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]

STAMP = "2026-11-24T12:00:00Z"
SHA40 = "0123456789abcdef0123456789abcdef01234567"
INTEGRATION_KEY = "w" * 32


def _make_record(payload_dict):
    raw = json.dumps(payload_dict).encode("utf-8")
    return SimpleNamespace(value=lambda: raw)


def _envelope(event_type, aggregate_id, payload, **overrides):
    data = {
        "event_id": str(uuid4()),
        "event_type": event_type,
        "event_version": 1,
        "aggregate_id": str(aggregate_id),
        "occurred_at": STAMP,
        "trace_id": str(uuid4()),
        "producer": "integration-service",
        "payload": payload,
    }
    data.update(overrides)
    return data


@pytest.fixture
def integration_activity_stub(settings):
    cache.clear()
    state = {
        "status": 200,
        "calls": [],
        "response_builder": None,
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            call = {
                "path": self.path,
                "service_key": self.headers.get("X-Service-Key"),
                "authorization": self.headers.get("Authorization"),
            }
            state["calls"].append(call)
            status = state["status"]
            if callable(state["response_builder"]):
                status, body = state["response_builder"](call)
            elif status == 200:
                body = {"success": True, "data": {}}
            else:
                body = {"success": False, "message": "Stub error"}
            encoded = json.dumps(body).encode("utf-8")
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
    settings.INTEGRATION_ADAPTER = "infrastructure.integration.RemoteIntegration"
    settings.WORK_INTEGRATION_BASE_URL = f"http://127.0.0.1:{port}"
    settings.WORK_INTEGRATION_SERVICE_KEY = INTEGRATION_KEY
    settings.WORK_GITHUB_ACTIVITY_CACHE_TTL_SECONDS = 45
    try:
        yield state
    finally:
        cache.clear()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_integration_account_changed_event_verifies_dedupes_ignores_stale_and_unlinks(
    created_project, classroom, actors, client_for
):
    second_group = GroupSnapshot(
        "group-2",
        "class-2",
        1,
        (GroupMemberFact(actors["leader"], "LEADER"), GroupMemberFact(actors["member"], "MEMBER")),
    )
    classroom.groups[second_group.group_id] = second_group
    second_project = client_for(actors["leader"]).post(
        "/projects/",
        {"identifier": "UT2", "name": "Dự án 2", "classroom_group_id": "group-2"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="proj-2",
    )
    assert second_project.status_code == 201
    second_id = second_project.json()["data"]["id"]

    member_client = client_for(actors["member"])
    for pid in (created_project["id"], second_id):
        res = member_client.patch(
            f"/projects/{pid}/members/{actors['member']}/github/",
            {"github_username": "student-dev"},
            format="json",
        )
        assert res.status_code == 200

    broker, dlq = Mock(), Mock()
    verify_event = _envelope(
        "integration.github.account.changed",
        actors["member"],
        {
            "user_id": str(actors["member"]),
            "github_user_id": "123456",
            "github_username": "Student-Dev",
            "source_version": 2,
            "verified": True,
            "synced_at": STAMP,
        },
    )
    record = _make_record(verify_event)
    process_connection_record(record, broker, dlq=dlq)
    dlq.publish.assert_not_called()
    broker.commit.assert_called_once_with(message=record, asynchronous=False)

    members = list(
        ProjectMember.objects.filter(user_id=actors["member"], status="ACTIVE").order_by(
            "project_id"
        )
    )
    assert len(members) == 2
    assert all(
        m.is_github_verified
        and m.github_user_id == "123456"
        and m.github_username == "Student-Dev"
        and m.github_source_version == 2
        for m in members
    )
    assert (
        OutboxEvent.objects.filter(event_type="project.member.github_mapping_updated").count() == 2
    )

    # Duplicate event_id is deduped cleanly.
    process_connection_record(_make_record(verify_event), broker, dlq=dlq)
    dlq.publish.assert_not_called()
    assert (
        OutboxEvent.objects.filter(event_type="project.member.github_mapping_updated").count() == 2
    )
    assert ConsumedEvent.objects.filter(event_id=verify_event["event_id"]).count() == 1

    # Stale source_version=1 unlink is ignored.
    stale_unlink = _envelope(
        "integration.github.account.changed",
        actors["member"],
        {
            "user_id": str(actors["member"]),
            "github_user_id": "123456",
            "github_username": "Student-Dev",
            "source_version": 1,
            "verified": False,
            "synced_at": STAMP,
        },
    )
    process_connection_record(_make_record(stale_unlink), broker, dlq=dlq)
    assert all(
        ProjectMember.objects.filter(user_id=actors["member"]).values_list(
            "is_github_verified", flat=True
        )
    )

    # Newer source_version=3 unlink clears verification on both projects.
    real_unlink = _envelope(
        "integration.github.account.changed",
        actors["member"],
        {
            "user_id": str(actors["member"]),
            "github_user_id": "123456",
            "github_username": "Student-Dev",
            "source_version": 3,
            "verified": False,
            "synced_at": STAMP,
        },
    )
    process_connection_record(_make_record(real_unlink), broker, dlq=dlq)
    assert not any(
        ProjectMember.objects.filter(user_id=actors["member"]).values_list(
            "is_github_verified", flat=True
        )
    )

    # Malformed payload routes to DLQ.
    bad_event = verify_event | {"event_id": str(uuid4()), "aggregate_id": str(uuid4())}
    process_connection_record(_make_record(bad_event), broker, dlq=dlq)
    dlq.publish.assert_called_once()


def test_integration_reference_detected_event_creates_pending_updates_and_confirms_to_kanban(
    github, actors, client_for
):
    _, _, _, task = github
    project = Project.objects.get(pk=task.project_id)
    assert project.identifier == "UT" and task.sequence_id == 1
    broker, dlq = Mock(), Mock()

    pr_event = _envelope(
        "integration.github.reference.detected",
        project.pk,
        {
            "project_id": str(project.pk),
            "repo_id": "123",
            "generation": 1,
            "source_version": 1,
            "task_code": "UT-1",
            "link_type": "PULL_REQUEST",
            "ref_id": "42",
            "title": "Fix UT-1 auth",
            "status": "OPEN",
            "url": "https://github.com/team/repo/pull/42",
            "is_verified": True,
            "synced_at": STAMP,
        },
    )
    commit_event = _envelope(
        "integration.github.reference.detected",
        project.pk,
        {
            "project_id": str(project.pk),
            "repo_id": "123",
            "generation": 1,
            "source_version": 1,
            "task_code": "UT-1",
            "link_type": "COMMIT",
            "ref_id": SHA40,
            "title": "feat: UT-1 commit",
            "status": None,
            "url": f"https://github.com/team/repo/commit/{SHA40}",
            "is_verified": True,
            "synced_at": STAMP,
        },
    )
    branch_event = _envelope(
        "integration.github.reference.detected",
        project.pk,
        {
            "project_id": str(project.pk),
            "repo_id": "123",
            "generation": 1,
            "source_version": 1,
            "task_code": "UT-1",
            "link_type": "BRANCH",
            "ref_id": "feat/UT-1-auth",
            "title": "feat/UT-1-auth",
            "status": None,
            "url": "https://github.com/team/repo/tree/feat/UT-1-auth",
            "is_verified": True,
            "synced_at": STAMP,
        },
    )
    for ev in (pr_event, commit_event, branch_event):
        process_connection_record(_make_record(ev), broker, dlq=dlq)
    dlq.publish.assert_not_called()

    links = list(TaskGitHubLink.objects.filter(task=task, deleted_at__isnull=True))
    assert len(links) == 3
    assert all(link.confirmation_status == "PENDING" and link.is_verified for link in links)

    # Newer PR status update transitions OPEN -> MERGED.
    pr_merged = _envelope(
        "integration.github.reference.detected",
        project.pk,
        pr_event["payload"] | {"source_version": 2, "status": "MERGED"},
    )
    process_connection_record(_make_record(pr_merged), broker, dlq=dlq)
    dlq.publish.assert_not_called()
    pr_link = TaskGitHubLink.objects.get(task=task, link_type="PULL_REQUEST", github_ref_id="42")
    assert pr_link.github_status == "MERGED"
    assert pr_link.confirmation_status == "PENDING"

    # Conflicting metadata at the same source_version routes to DLQ.
    pr_conflict = _envelope(
        "integration.github.reference.detected",
        project.pk,
        pr_merged["payload"] | {"title": "Conflicting title at same version"},
    )
    process_connection_record(_make_record(pr_conflict), broker, dlq=dlq)
    dlq.publish.assert_called_once()

    # Benign non-matching task codes / repo / generation do not DLQ.
    dlq.reset_mock()
    for benign_change in (
        {"task_code": "OTHER-1"},
        {"task_code": "UT-999"},
        {"repo_id": "999"},
        {"generation": 99},
    ):
        ev = _envelope(
            "integration.github.reference.detected",
            project.pk,
            pr_event["payload"] | benign_change,
        )
        process_connection_record(_make_record(ev), broker, dlq=dlq)
    dlq.publish.assert_not_called()

    # Member confirms the candidate PR link -> Kanban reflects has_pull_request=True.
    member = client_for(actors["member"])
    confirm = member.post(
        f"/tasks/{task.pk}/github-links/{pr_link.pk}/confirm/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY="confirm-pr-42",
    )
    assert confirm.status_code == 200, confirm.content
    assert confirm.json()["data"]["confirmation_status"] == "CONFIRMED"

    kanban = member.get(f"/projects/{project.pk}/kanban/")
    assert kanban.status_code == 200
    tasks_on_board = [t for col in kanban.json()["data"]["columns"] for t in col["tasks"]]
    matched = [t for t in tasks_on_board if t["id"] == str(task.pk)]
    assert len(matched) == 1 and matched[0]["has_pull_request"] is True

    # Disconnected project skips reference events without DLQ.
    Project.objects.filter(pk=project.pk).update(github_connection_status="DISCONNECTED")
    after_disconnect = _envelope(
        "integration.github.reference.detected",
        project.pk,
        pr_event["payload"] | {"ref_id": "99", "url": "https://github.com/team/repo/pull/99"},
    )
    process_connection_record(_make_record(after_disconnect), broker, dlq=dlq)
    dlq.publish.assert_not_called()
    assert not TaskGitHubLink.objects.filter(task=task, github_ref_id="99").exists()


def test_github_activity_api_disconnected_and_pending_skip_integration_call(
    created_project, actors, client_for, integration_activity_stub
):
    project_id = created_project["id"]
    member = client_for(actors["member"])

    disconnected = member.get(f"/projects/{project_id}/github/activity/")
    assert disconnected.status_code == 200, disconnected.content
    body = disconnected.json()
    assert body["message"] == "Đã lấy thông tin hoạt động GitHub của dự án."
    assert body["data"]["status"] == "DISCONNECTED"
    assert body["data"]["connection_generation"] == 0
    assert body["data"]["cached"] is False
    assert body["data"]["branches"] == []
    assert body["data"]["commits"] == []
    assert body["data"]["pull_requests"] == []
    assert body["data"]["issues"] == []
    assert len(integration_activity_stub["calls"]) == 0

    Project.objects.filter(pk=project_id).update(
        github_connection_status="PENDING",
        github_connection_generation=1,
        github_repo_id="123",
    )
    pending = member.get(f"/projects/{project_id}/github/activity/")
    assert pending.status_code == 200
    assert pending.json()["data"]["status"] == "PENDING"
    assert pending.json()["data"]["connection_generation"] == 1
    assert len(integration_activity_stub["calls"]) == 0


def test_github_activity_api_real_http_cache_linked_tasks_and_generation_isolation(
    github, actors, client_for, integration_activity_stub
):
    _, _, _, task = github
    project = Project.objects.get(pk=task.project_id)

    # 1 confirmed branch, 1 confirmed short-SHA commit, 1 pending PR (excluded until confirmed).
    TaskGitHubLink.objects.create(
        task=task,
        github_repo_id="123",
        connection_generation=1,
        source_version=1,
        confirmation_status="CONFIRMED",
        confirmed_by_user_id=actors["leader"],
        confirmed_at="2026-11-24T12:00:00Z",
        link_type="BRANCH",
        github_ref_id="feat/UT-1",
        github_title="feat/UT-1",
        github_url="https://github.com/team/repo/tree/feat/UT-1",
        is_verified=True,
        synced_at="2026-11-24T12:00:00Z",
    )
    TaskGitHubLink.objects.create(
        task=task,
        github_repo_id="123",
        connection_generation=1,
        source_version=1,
        confirmation_status="CONFIRMED",
        confirmed_by_user_id=actors["leader"],
        confirmed_at="2026-11-24T12:00:00Z",
        link_type="COMMIT",
        github_ref_id=SHA40[:7],
        github_title="feat: short sha",
        github_url=f"https://github.com/team/repo/commit/{SHA40[:7]}",
        is_verified=True,
        synced_at="2026-11-24T12:00:00Z",
    )
    pending_pr = TaskGitHubLink.objects.create(
        task=task,
        github_repo_id="123",
        connection_generation=1,
        source_version=1,
        confirmation_status="PENDING",
        link_type="PULL_REQUEST",
        github_ref_id="42",
        github_title="PR 42",
        github_status="OPEN",
        github_url="https://github.com/team/repo/pull/42",
        is_verified=True,
        synced_at="2026-11-24T12:00:00Z",
    )

    current_gen = {"value": 1, "repo_id": "123"}

    def build_activity(_call):
        return (
            200,
            {
                "success": True,
                "data": {
                    "project_id": str(project.pk),
                    "repo_id": current_gen["repo_id"],
                    "repo_owner": "team",
                    "repo_name": "repo",
                    "default_branch": "main",
                    "generation": current_gen["value"],
                    "status": "CONNECTED",
                    "open_pull_requests_count": 1,
                    "branches": [
                        {
                            "name": "feat/UT-1",
                            "sha": SHA40,
                            "url": "https://github.com/team/repo/tree/feat/UT-1",
                        }
                    ],
                    "commits": [
                        {
                            "id": SHA40,
                            "title": "feat: UT-1 commit",
                            "url": f"https://github.com/team/repo/commit/{SHA40}",
                            "occurred_at": STAMP,
                        }
                    ],
                    "pull_requests": [
                        {
                            "id": "42",
                            "title": "Fix UT-1",
                            "status": "OPEN",
                            "url": "https://github.com/team/repo/pull/42",
                            "occurred_at": STAMP,
                        }
                    ],
                    "issues": [
                        {
                            "id": "9",
                            "title": "Open issue",
                            "status": "OPEN",
                            "url": "https://github.com/team/repo/issues/9",
                            "occurred_at": STAMP,
                        }
                    ],
                    "synced_at": STAMP,
                },
            },
        )

    integration_activity_stub["response_builder"] = build_activity
    route = f"/projects/{project.pk}/github/activity/"
    member = client_for(actors["member"])

    first = member.get(route)
    assert first.status_code == 200, first.content
    data1 = first.json()["data"]
    assert data1["cached"] is False
    assert data1["branches"][0]["linked_task_ids"] == [str(task.pk)]
    assert data1["commits"][0]["linked_task_ids"] == [str(task.pk)]
    assert data1["pull_requests"][0]["linked_task_ids"] == []
    assert len(integration_activity_stub["calls"]) == 1
    assert integration_activity_stub["calls"][0]["service_key"] == INTEGRATION_KEY
    assert integration_activity_stub["calls"][0]["authorization"].startswith("Bearer ")

    # Confirm PR link; cached activity must still merge the fresh confirmed task link immediately.
    confirm = member.post(
        f"/tasks/{task.pk}/github-links/{pending_pr.pk}/confirm/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY="confirm-activity-pr",
    )
    assert confirm.status_code == 200

    second = member.get(route)
    assert second.status_code == 200
    data2 = second.json()["data"]
    assert data2["cached"] is True
    assert data2["pull_requests"][0]["linked_task_ids"] == [str(task.pk)]
    assert len(integration_activity_stub["calls"]) == 1

    # Assigned teacher can read; outsider receives 404.
    teacher_res = client_for(actors["teacher"]).get(route)
    assert teacher_res.status_code == 200 and teacher_res.json()["data"]["cached"] is True
    outsider_res = client_for(actors["outsider"]).get(route)
    assert outsider_res.status_code == 404

    # Incrementing connection generation isolates cache key and refetches live data.
    current_gen["value"] = 2
    Project.objects.filter(pk=project.pk).update(github_connection_generation=2)
    third = member.get(route)
    assert third.status_code == 200
    assert third.json()["data"]["cached"] is False
    assert third.json()["data"]["connection_generation"] == 2
    assert len(integration_activity_stub["calls"]) == 2

    # Mismatched repo_id fails closed and is never cached.
    current_gen["repo_id"] = "999"
    Project.objects.filter(pk=project.pk).update(github_connection_generation=3)
    current_gen["value"] = 3
    mismatch = member.get(route)
    assert mismatch.status_code == 503
    assert mismatch.json()["error"]["code"] == "INTEGRATION_UNAVAILABLE"


def test_github_activity_api_cache_policy_fail_open_and_error_mapping(
    github, actors, client_for, integration_activity_stub, monkeypatch
):
    _, _, _, task = github
    project_id = task.project_id
    route = f"/projects/{project_id}/github/activity/"
    member = client_for(actors["member"])

    def set_status(activity_status):
        integration_activity_stub["response_builder"] = lambda _call: (
            200,
            {
                "success": True,
                "data": {
                    "project_id": str(project_id),
                    "repo_id": "123",
                    "repo_owner": "team",
                    "repo_name": "repo",
                    "default_branch": "main",
                    "generation": 1,
                    "status": activity_status,
                    "open_pull_requests_count": 0,
                    "branches": [],
                    "commits": [],
                    "pull_requests": [],
                    "issues": [],
                    "synced_at": STAMP,
                },
            },
        )

    # PARTIAL is cached.
    set_status("PARTIAL")
    assert member.get(route).json()["data"]["cached"] is False
    assert member.get(route).json()["data"]["cached"] is True
    assert len(integration_activity_stub["calls"]) == 1

    # STALE and REAUTH_REQUIRED are never cached.
    for uncached_status in ("STALE", "REAUTH_REQUIRED"):
        cache.clear()
        integration_activity_stub["calls"].clear()
        set_status(uncached_status)
        r1 = member.get(route)
        r2 = member.get(route)
        assert r1.status_code == 200 and r1.json()["data"]["cached"] is False
        assert r2.status_code == 200 and r2.json()["data"]["cached"] is False
        assert len(integration_activity_stub["calls"]) == 2

    # Cache failure degrades gracefully to live fetch.
    cache.clear()
    integration_activity_stub["calls"].clear()
    set_status("CONNECTED")

    def boom(*args, **kwargs):
        raise RuntimeError("redis offline")

    monkeypatch.setattr("apps.integrations.services.activity.cache.get", boom)
    monkeypatch.setattr("apps.integrations.services.activity.cache.set", boom)
    degraded = member.get(route)
    assert degraded.status_code == 200 and degraded.json()["data"]["cached"] is False
    assert len(integration_activity_stub["calls"]) == 1

    # Integration error responses propagate cleanly with Vietnamese messages.
    integration_activity_stub["response_builder"] = None
    for http_status, expected in ((401, 401), (403, 403), (404, 404), (429, 429), (500, 503)):
        integration_activity_stub["status"] = http_status
        res = member.get(route)
        assert res.status_code == expected, res.content
        assert any("À" <= char <= "ỹ" for char in res.json()["message"])
        assert INTEGRATION_KEY not in res.json()["message"]


def test_integration_reused_event_id_with_different_payload_routes_to_dlq(
    github, actors, client_for
):
    _, _, _, task = github
    project = Project.objects.get(pk=task.project_id)
    assert (
        client_for(actors["member"])
        .patch(
            f"/projects/{project.pk}/members/{actors['member']}/github/",
            {"github_username": "student-dlq"},
            format="json",
        )
        .status_code
        == 200
    )
    broker, dlq = Mock(), Mock()

    acc_event = _envelope(
        "integration.github.account.changed",
        actors["member"],
        {
            "user_id": str(actors["member"]),
            "github_user_id": "222333",
            "github_username": "student-dlq",
            "source_version": 1,
            "verified": True,
            "synced_at": STAMP,
        },
    )
    process_connection_record(_make_record(acc_event), broker, dlq=dlq)
    dlq.publish.assert_not_called()

    tampered_acc = {
        **acc_event,
        "payload": acc_event["payload"] | {"verified": False, "source_version": 2},
    }
    process_connection_record(_make_record(tampered_acc), broker, dlq=dlq)
    assert dlq.publish.call_count == 1
    assert ProjectMember.objects.get(project=project, user_id=actors["member"]).is_github_verified

    ref_event = _envelope(
        "integration.github.reference.detected",
        project.pk,
        {
            "project_id": str(project.pk),
            "repo_id": "123",
            "generation": 1,
            "source_version": 1,
            "task_code": "UT-1",
            "link_type": "PULL_REQUEST",
            "ref_id": "55",
            "title": "PR 55",
            "status": "OPEN",
            "url": "https://github.com/team/repo/pull/55",
            "is_verified": True,
            "synced_at": STAMP,
        },
    )
    process_connection_record(_make_record(ref_event), broker, dlq=dlq)
    assert dlq.publish.call_count == 1

    tampered_ref = {
        **ref_event,
        "payload": ref_event["payload"] | {"status": "MERGED", "source_version": 2},
    }
    process_connection_record(_make_record(tampered_ref), broker, dlq=dlq)
    assert dlq.publish.call_count == 2
    assert (
        TaskGitHubLink.objects.get(
            task=task, link_type="PULL_REQUEST", github_ref_id="55"
        ).github_status
        == "OPEN"
    )


@pytest.mark.postgres
def test_integration_consumer_concurrent_delivery_is_idempotent_and_monotonic(
    github, actors, client_for
):
    _, _, _, task = github
    project = Project.objects.get(pk=task.project_id)
    assert (
        client_for(actors["member"])
        .patch(
            f"/projects/{project.pk}/members/{actors['member']}/github/",
            {"github_username": "race-student"},
            format="json",
        )
        .status_code
        == 200
    )

    acc_event = _envelope(
        "integration.github.account.changed",
        actors["member"],
        {
            "user_id": str(actors["member"]),
            "github_user_id": "998877",
            "github_username": "Race-Student",
            "source_version": 2,
            "verified": True,
            "synced_at": STAMP,
        },
    )
    barrier_acc = Barrier(2)

    def deliver_acc(_idx):
        close_old_connections()
        try:
            broker, dlq = Mock(), Mock()
            barrier_acc.wait(timeout=10)
            process_connection_record(_make_record(acc_event), broker, dlq=dlq)
            return dlq.publish.call_count
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        dlq_counts = list(pool.map(deliver_acc, [1, 2]))
    assert dlq_counts == [0, 0]
    assert ConsumedEvent.objects.filter(event_id=acc_event["event_id"]).count() == 1
    assert (
        OutboxEvent.objects.filter(
            project=project, event_type="project.member.github_mapping_updated"
        ).count()
        == 1
    )

    ref_v1 = _envelope(
        "integration.github.reference.detected",
        project.pk,
        {
            "project_id": str(project.pk),
            "repo_id": "123",
            "generation": 1,
            "source_version": 1,
            "task_code": "UT-1",
            "link_type": "PULL_REQUEST",
            "ref_id": "88",
            "title": "PR 88 open",
            "status": "OPEN",
            "url": "https://github.com/team/repo/pull/88",
            "is_verified": True,
            "synced_at": STAMP,
        },
    )
    ref_v2 = _envelope(
        "integration.github.reference.detected",
        project.pk,
        ref_v1["payload"] | {"source_version": 2, "status": "MERGED", "title": "PR 88 merged"},
    )
    barrier_ref = Barrier(2)

    def deliver_ref(ev):
        close_old_connections()
        try:
            broker, dlq = Mock(), Mock()
            barrier_ref.wait(timeout=10)
            process_connection_record(_make_record(ev), broker, dlq=dlq)
            return dlq.publish.call_count
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        ref_dlqs = list(pool.map(deliver_ref, [ref_v1, ref_v2]))
    assert ref_dlqs == [0, 0]
    pr_links = list(
        TaskGitHubLink.objects.filter(
            task=task, link_type="PULL_REQUEST", github_ref_id="88", deleted_at__isnull=True
        )
    )
    assert len(pr_links) == 1
    assert pr_links[0].source_version == 2 and pr_links[0].github_status == "MERGED"


def test_github_activity_api_pending_operation_overrides_connected_and_validates_openapi_schema(
    github, actors, client_for, integration_activity_stub
):
    _, _, _, task = github
    project = Project.objects.get(pk=task.project_id)
    route = f"/projects/{project.pk}/github/activity/"
    member = client_for(actors["member"])

    contract_path = Path(__file__).resolve().parents[4] / "contracts" / "api" / "work-service.yaml"
    spec = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(
        {
            "$ref": "#/components/schemas/ProjectGitHubActivityEnvelope",
            "components": {"schemas": spec["components"]["schemas"]},
        }
    )

    for status in ("CONNECTED", "PARTIAL", "STALE", "REAUTH_REQUIRED"):
        cache.clear()
        integration_activity_stub["response_builder"] = lambda _call, st=status: (
            200,
            {
                "success": True,
                "data": {
                    "project_id": str(project.pk),
                    "repo_id": "123",
                    "repo_owner": "team",
                    "repo_name": "repo",
                    "default_branch": "main",
                    "generation": 1,
                    "status": st,
                    "open_pull_requests_count": 1,
                    "branches": [
                        {
                            "name": "main",
                            "sha": SHA40,
                            "url": "https://github.com/team/repo/tree/main",
                        }
                    ],
                    "commits": [
                        {
                            "id": SHA40,
                            "title": "feat: commit",
                            "url": f"https://github.com/team/repo/commit/{SHA40}",
                            "occurred_at": STAMP,
                        }
                    ],
                    "pull_requests": [
                        {
                            "id": "42",
                            "title": "PR 42",
                            "status": "OPEN",
                            "url": "https://github.com/team/repo/pull/42",
                            "occurred_at": STAMP,
                        }
                    ],
                    "issues": [
                        {
                            "id": "7",
                            "title": "Issue 7",
                            "status": "OPEN",
                            "url": "https://github.com/team/repo/issues/7",
                            "occurred_at": STAMP,
                        }
                    ],
                    "synced_at": STAMP,
                },
            },
        )
        res = member.get(route)
        assert res.status_code == 200, res.content
        validator.validate(res.json())

    # Warm cache with CONNECTED, then create an active PENDING operation -> must return PENDING!
    cache.clear()
    integration_activity_stub["calls"].clear()
    integration_activity_stub["response_builder"] = lambda _call: (
        200,
        {
            "success": True,
            "data": {
                "project_id": str(project.pk),
                "repo_id": "123",
                "repo_owner": "team",
                "repo_name": "repo",
                "default_branch": "main",
                "generation": 1,
                "status": "CONNECTED",
                "open_pull_requests_count": 0,
                "branches": [],
                "commits": [],
                "pull_requests": [],
                "issues": [],
                "synced_at": STAMP,
            },
        },
    )
    assert member.get(route).json()["data"]["status"] == "CONNECTED"
    assert len(integration_activity_stub["calls"]) == 1

    GitHubConnectionOperation.objects.create(
        project=project,
        operation_id="disconnect-in-flight",
        actor_user_id=actors["leader"],
        action="DISCONNECT",
        payload_hash="h" * 64,
        request_body={"operation_id": "disconnect-in-flight"},
        state="CONFIRM",
        generation=2,
        prepared={
            "repo_id": None,
            "repo_owner": None,
            "repo_name": None,
            "default_branch": None,
            "generation": 2,
            "source_version": 1,
            "synced_at": STAMP,
        },
    )
    pending_res = member.get(route)
    assert pending_res.status_code == 200, pending_res.content
    validator.validate(pending_res.json())
    assert pending_res.json()["data"]["status"] == "PENDING"
    assert pending_res.json()["data"]["connection_generation"] == 2
    assert pending_res.json()["data"]["cached"] is False
    assert len(integration_activity_stub["calls"]) == 1

    # Corrupt edge case: status="CONNECTED" with repo_id=None must safely return DISCONNECTED.
    GitHubConnectionOperation.objects.filter(operation_id="disconnect-in-flight").delete()
    Project.objects.filter(pk=project.pk).update(
        github_connection_status="CONNECTED", github_repo_id=None
    )
    disconnected_res = member.get(route)
    assert disconnected_res.status_code == 200
    validator.validate(disconnected_res.json())
    assert disconnected_res.json()["data"]["status"] == "DISCONNECTED"
    assert len(integration_activity_stub["calls"]) == 1
