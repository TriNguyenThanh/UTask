"""Integration tests for Work domain workflows and PostgreSQL write guards."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from allauth.account.models import EmailAddress
from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import AccountStatus, User
from apps.activities.models import WorkActivity
from apps.collaboration.models import Attachment, Comment
from apps.courses.models import ClassSection, ClassTeacher, Course, Enrollment
from apps.groups.models import GroupMember, GroupProjectLink, StudyGroup
from apps.integrations.consumer import process_integration_record
from apps.integrations.models import TaskGitHubLink
from apps.messaging.models import ConsumedEvent, OutboxEvent, OutboxProducer
from apps.projects.models import Project, ProjectMember, State
from apps.sprints.models import Sprint, SprintTask
from apps.tasks.models import Task
from apps.tasks.tasks import scan_deadlines
from infrastructure.ai import VerifiedProposal
from infrastructure.integration import ConnectionFact, ReferenceFact
from infrastructure.storage import ObjectFacts

pytestmark = pytest.mark.integration

TEST_PASSWORD = "StrongPassword123!"
INTEGRATION_SERVICE_KEY = "test-work-integration-inbound-key-000000001"


def _idem_headers(key: str | None = None) -> dict[str, str]:
    return {"HTTP_IDEMPOTENCY_KEY": key or str(uuid4())}


def _create_user(
    *,
    first_name: str,
    last_name: str,
    role: str = "STUDENT",
    student_id: str | None = None,
) -> User:
    suffix = uuid4().hex[:8]
    user = User.objects.create_user(
        email=f"{role.lower()}_{suffix}@utask.edu.vn",
        username=f"{role.lower()}_{suffix}",
        password=TEST_PASSWORD,
        student_id=student_id,
        first_name=first_name,
        last_name=last_name,
        global_role_code=role,
        account_status=AccountStatus.ACTIVE,
    )
    EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
    return user


def _login_client(user: User) -> APIClient:
    auth_client = APIClient()
    response = auth_client.post(
        "/api/auth/login",
        {"email": user.email, "password": TEST_PASSWORD},
        format="json",
    )
    assert response.status_code == 200, response.content
    access_token = response.json()["data"]["access"]
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    client.user = user
    client.access_token = access_token
    return client


@dataclass
class WorkFixtureBundle:
    teacher: User
    leader: User
    member: User
    outsider: User
    teacher_client: APIClient
    leader_client: APIClient
    member_client: APIClient
    outsider_client: APIClient
    course: Course
    section: ClassSection
    group: StudyGroup

    def create_project(
        self,
        *,
        identifier: str | None = None,
        name: str = "UTask Capstone",
        idempotency_key: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        resolved_identifier = identifier or f"P{uuid4().hex[:6].upper()}"
        resolved_start = start_date or date.today()
        resolved_end = end_date or (resolved_start + timedelta(days=90))
        response = self.leader_client.post(
            "/api/work/projects/",
            {
                "identifier": resolved_identifier,
                "name": name,
                "description": "Capstone project workspace",
                "target_goals": "Deliver reliable modular monolith",
                "tech_stack": {"backend": "Django", "db": "PostgreSQL"},
                "start_date": resolved_start.isoformat(),
                "end_date": resolved_end.isoformat(),
                "classroom_group_id": str(self.group.pk),
            },
            format="json",
            **_idem_headers(idempotency_key),
        )
        assert response.status_code == 201, response.content
        return response.json()["data"]

    def create_task(
        self,
        project_id: str,
        *,
        title: str = "Implement module",
        client: APIClient | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        active_client = client or self.leader_client
        payload = {"title": title, **extra}
        response = active_client.post(
            f"/api/work/projects/{project_id}/tasks/",
            payload,
            format="json",
            **_idem_headers(),
        )
        assert response.status_code == 201, response.content
        return response.json()["data"]


@pytest.fixture
def work_workspace(db) -> WorkFixtureBundle:
    teacher = _create_user(first_name="Lan", last_name="Pham", role="TEACHER")
    leader = _create_user(
        first_name="An",
        last_name="Nguyen",
        role="STUDENT",
        student_id=f"SV{uuid4().hex[:6].upper()}",
    )
    member = _create_user(
        first_name="Binh",
        last_name="Tran",
        role="STUDENT",
        student_id=f"SV{uuid4().hex[:6].upper()}",
    )
    outsider = _create_user(
        first_name="Cuong",
        last_name="Le",
        role="STUDENT",
        student_id=f"SV{uuid4().hex[:6].upper()}",
    )
    course = Course.objects.create(
        created_by_id=teacher.pk,
        code=f"SE{uuid4().hex[:6].upper()}",
        name="Software Engineering",
    )
    today = date.today()
    section = ClassSection.objects.create(
        course=course,
        code=f"CLS-{uuid4().hex[:6].upper()}",
        name="SE Section 01",
        term="2026-HK1",
        starts_on=today - timedelta(days=7),
        ends_on=today + timedelta(days=120),
        status="OPEN",
        grouping_phase="FORMING",
        group_min_size=1,
        group_max_size=6,
    )
    ClassTeacher.objects.create(
        class_section=section,
        user_id=teacher.pk,
        role="PRIMARY",
        status="ACTIVE",
    )
    leader_enrollment = Enrollment.objects.create(
        class_section=section,
        user_id=leader.pk,
        status="ACTIVE",
        source="TEACHER",
    )
    member_enrollment = Enrollment.objects.create(
        class_section=section,
        user_id=member.pk,
        status="ACTIVE",
        source="TEACHER",
    )
    group = StudyGroup.objects.create(
        class_section=section,
        name="Alpha Team",
        status="ACTIVE",
        source_version=1,
    )
    GroupMember.objects.create(
        class_section=section,
        group=group,
        enrollment=leader_enrollment,
        role="LEADER",
        status="ACTIVE",
    )
    GroupMember.objects.create(
        class_section=section,
        group=group,
        enrollment=member_enrollment,
        role="MEMBER",
        status="ACTIVE",
    )
    return WorkFixtureBundle(
        teacher=teacher,
        leader=leader,
        member=member,
        outsider=outsider,
        teacher_client=_login_client(teacher),
        leader_client=_login_client(leader),
        member_client=_login_client(member),
        outsider_client=_login_client(outsider),
        course=course,
        section=section,
        group=group,
    )


class InMemoryStorageFake:
    """In-memory storage fake matching infrastructure.storage.R2Storage interface."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[int, str, bool]] = {}
        self.deleted_keys: list[str] = []

    def put_valid_object(self, storage_key: str, *, size: int, content_type: str) -> None:
        self.objects[storage_key] = (size, content_type, True)

    def presign(self, attachment: Attachment) -> tuple[str, dict[str, str]]:
        headers = {
            "Content-Type": attachment.content_type,
            "Content-Length": str(attachment.file_size),
            "If-None-Match": "*",
        }
        return f"https://storage.local/upload/{attachment.storage_key}", headers

    def inspect(self, attachment: Attachment) -> ObjectFacts:
        size, content_type, valid = self.objects[attachment.storage_key]
        return ObjectFacts(size=size, content_type=content_type, valid_content=valid)

    def download(self, attachment: Attachment) -> str:
        return f"https://storage.local/download/{attachment.storage_key}"

    def delete(self, key: str) -> None:
        self.deleted_keys.append(key)
        self.objects.pop(key, None)


class FakeAIProposalClient:
    """Fake AI verifier returning pre-registered VerifiedProposal objects."""

    accepts_bearer = True

    def __init__(self) -> None:
        self.proofs: dict[tuple[str, str], VerifiedProposal] = {}
        self.calls: list[dict[str, Any]] = []

    def register(self, proof: VerifiedProposal) -> None:
        self.proofs[(proof.proposal_id, proof.kind)] = proof

    def verify(
        self,
        *,
        actor,
        project_id,
        proposal_id,
        kind,
        parent_id=None,
        bearer=None,
    ) -> VerifiedProposal:
        self.calls.append(
            {
                "actor_id": actor.id,
                "project_id": project_id,
                "proposal_id": proposal_id,
                "kind": kind,
                "parent_id": parent_id,
            }
        )
        return self.proofs[(proposal_id, kind)]


class FakeIntegrationClient:
    """Fake Integration Service HTTP adapter for repo connection & reference verification."""

    def __init__(self) -> None:
        self.version = 0
        self.prepared_facts: dict[str, ConnectionFact] = {}
        self.reference_facts: dict[tuple[str, str], ReferenceFact] = {}

    def prepare(self, *, project_id, body, bearer) -> ConnectionFact:
        self.version += 1
        is_connect = body["action"] == "CONNECT"
        fact = ConnectionFact(
            project_id=project_id,
            operation_id=body["operation_id"],
            generation=body["expected_generation"] + 1,
            source_version=self.version,
            status="PENDING",
            repo_id=body["github_repo_id"] if is_connect else None,
            repo_owner="utask-org" if is_connect else None,
            repo_name="capstone-repo" if is_connect else None,
            default_branch="main" if is_connect else None,
            synced_at=timezone.now(),
        )
        self.prepared_facts[body["operation_id"]] = fact
        return fact

    def register_reference(self, fact: ReferenceFact) -> None:
        self.reference_facts[(fact.link_type, fact.ref_id)] = fact

    def verify_reference(
        self,
        *,
        project_id,
        repo_id,
        generation,
        link_type,
        github_ref_id,
        bearer,
        actor=None,
    ) -> ReferenceFact:
        return self.reference_facts[(link_type, github_ref_id)]


class FakeKafkaRecord:
    """Minimal confluent_kafka Message stand-in for process_integration_record tests."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def value(self) -> bytes:
        return self._payload


class FakeKafkaConsumer:
    def __init__(self) -> None:
        self.committed: list[FakeKafkaRecord] = []

    def commit(self, *, message, asynchronous: bool = False) -> None:
        self.committed.append(message)


class FakeDLQPublisher:
    def __init__(self) -> None:
        self.entries: list[tuple[FakeKafkaRecord, str]] = []

    def publish(self, record, *, reason: str) -> None:
        self.entries.append((record, reason))


def test_project_lifecycle_states_capacity_board_dashboard_overview_and_oversight(
    work_workspace: WorkFixtureBundle,
):
    idem_key = str(uuid4())
    start_day = date.today()
    end_day = start_day + timedelta(days=90)
    project_data = work_workspace.create_project(
        identifier="WRK1",
        name="Work Integration Project",
        idempotency_key=idem_key,
        start_date=start_day,
        end_date=end_day,
    )
    project_id = project_data["id"]

    # Idempotent replay returns identical project without duplicating rows.
    replay = work_workspace.leader_client.post(
        "/api/work/projects/",
        {
            "identifier": "WRK1",
            "name": "Work Integration Project",
            "description": "Capstone project workspace",
            "target_goals": "Deliver reliable modular monolith",
            "tech_stack": {"backend": "Django", "db": "PostgreSQL"},
            "start_date": start_day.isoformat(),
            "end_date": end_day.isoformat(),
            "classroom_group_id": str(work_workspace.group.pk),
        },
        format="json",
        **_idem_headers(idem_key),
    )
    assert replay.status_code == 201
    assert replay.json()["data"]["id"] == project_id
    assert Project.objects.filter(pk=project_id).count() == 1

    # Verify auto-created default states, synced ProjectMembers, and Classroom GroupProjectLink.
    states = list(
        State.objects.filter(project_id=project_id, deleted_at__isnull=True).order_by("sequence")
    )
    assert [state.name for state in states] == [
        "Backlog",
        "To Do",
        "In Progress",
        "Code Review",
        "Done",
    ]
    assert states[0].is_default is True
    assert sum(state.is_default for state in states) == 1

    members_by_uid = {
        row.user_id: (row.role, row.status)
        for row in ProjectMember.objects.filter(project_id=project_id)
    }
    assert members_by_uid == {
        work_workspace.leader.pk: ("LEADER", "ACTIVE"),
        work_workspace.member.pk: ("MEMBER", "ACTIVE"),
    }
    assert GroupProjectLink.objects.filter(
        project_id=project_id,
        group=work_workspace.group,
        class_section=work_workspace.section,
    ).exists()

    # Project list & detail visible to members and teacher, hidden from outsider.
    assert work_workspace.leader_client.get("/api/work/projects/").status_code == 200
    detail = work_workspace.member_client.get(f"/api/work/projects/{project_id}/")
    assert detail.status_code == 200
    assert detail.json()["data"]["identifier"] == "WRK1"
    outsider_detail = work_workspace.outsider_client.get(f"/api/work/projects/{project_id}/")
    assert outsider_detail.status_code == 404

    # Project detail update bumps version.
    patched = work_workspace.leader_client.patch(
        f"/api/work/projects/{project_id}/",
        {
            "name": "Work Project Renamed",
            "target_goals": "Ship v1 cleanly",
            "expected_version": project_data["version"],
        },
        format="json",
    )
    assert patched.status_code == 200
    version_after_patch = patched.json()["data"]["version"]
    assert version_after_patch == project_data["version"] + 1
    assert patched.json()["data"]["name"] == "Work Project Renamed"

    # Archive blocks writes; unarchive restores writes.
    archived = work_workspace.leader_client.post(
        f"/api/work/projects/{project_id}/archive/",
        {"expected_version": version_after_patch},
        format="json",
    )
    assert archived.status_code == 200
    assert archived.json()["data"]["archived_at"] is not None
    version_after_archive = archived.json()["data"]["version"]

    blocked_write = work_workspace.leader_client.post(
        f"/api/work/projects/{project_id}/tasks/",
        {"title": "Cannot create while archived"},
        format="json",
        **_idem_headers(),
    )
    assert blocked_write.status_code == 400

    unarchived = work_workspace.leader_client.post(
        f"/api/work/projects/{project_id}/unarchive/",
        {"expected_version": version_after_archive},
        format="json",
    )
    assert unarchived.status_code == 200
    assert unarchived.json()["data"]["archived_at"] is None

    # States CRUD + task migration on state deletion.
    listed_states = work_workspace.leader_client.get(f"/api/work/projects/{project_id}/states/")
    assert listed_states.status_code == 200
    assert len(listed_states.json()["data"]) == 5

    created_state = work_workspace.leader_client.post(
        f"/api/work/projects/{project_id}/states/",
        {"name": "QA Testing", "color": "#10B981", "sequence": 35000.0, "group": "REVIEW"},
        format="json",
    )
    assert created_state.status_code == 201
    custom_state_id = created_state.json()["data"]["id"]

    updated_state = work_workspace.leader_client.patch(
        f"/api/work/projects/{project_id}/states/{custom_state_id}/",
        {"name": "QA Verification", "color": "#059669"},
        format="json",
    )
    assert updated_state.status_code == 200
    assert updated_state.json()["data"]["name"] == "QA Verification"

    todo_state = next(s for s in states if s.name == "To Do")
    task_in_custom = work_workspace.create_task(
        project_id,
        title="Verify release candidate",
        state_id=custom_state_id,
        story_points=5,
        due_date=date.today().isoformat(),
        assignee_ids=[str(work_workspace.member.pk)],
    )
    delete_without_target = work_workspace.leader_client.delete(
        f"/api/work/projects/{project_id}/states/{custom_state_id}/"
    )
    assert delete_without_target.status_code == 400
    assert delete_without_target.json()["error"]["code"] == "STATE_HAS_EXISTING_TASKS"

    delete_with_target = work_workspace.leader_client.delete(
        f"/api/work/projects/{project_id}/states/{custom_state_id}/?target_state_id={todo_state.pk}"
    )
    assert delete_with_target.status_code == 200
    assert delete_with_target.json()["data"]["migrated_tasks_count"] == 1
    assert Task.objects.get(pk=task_in_custom["id"]).state_id == todo_state.pk

    # Member capacity update.
    cap_resp = work_workspace.leader_client.patch(
        f"/api/work/projects/{project_id}/members/{work_workspace.member.pk}/capacity/",
        {"weekly_capacity": 16},
        format="json",
    )
    assert cap_resp.status_code == 200
    assert cap_resp.json()["data"]["weekly_capacity"] == 16

    # Kanban board & column views.
    board = work_workspace.member_client.get(f"/api/work/projects/{project_id}/kanban/")
    assert board.status_code == 200
    board_data = board.json()["data"]
    assert board_data["total_columns"] == 5
    assert board_data["total_tasks"] == 1

    column = work_workspace.member_client.get(
        f"/api/work/projects/{project_id}/kanban/states/{todo_state.pk}/tasks/"
    )
    assert column.status_code == 200
    assert column.json()["data"]["column_total_tasks"] == 1
    assert column.json()["data"]["tasks"][0]["id"] == task_in_custom["id"]
    assert column.json()["data"]["tasks"][0]["assignees"][0]["display_name"] == "Tran Binh"

    # Dashboard metrics.
    dashboard = work_workspace.leader_client.get(f"/api/work/projects/{project_id}/dashboard/")
    assert dashboard.status_code == 200
    dash_data = dashboard.json()["data"]
    assert dash_data["totals"]["work_item_count"] == 1
    assert dash_data["totals"]["known_estimate_points"] == 5
    assert dash_data["assignee_distribution"][0]["user_id"] == str(work_workspace.member.pk)
    assert dash_data["assignee_distribution"][0]["weekly_capacity"] == 16

    # Me overview for member.
    overview = work_workspace.member_client.get("/api/work/me/overview/")
    assert overview.status_code == 200
    overview_data = overview.json()["data"]
    assert overview_data["task_counts"]["total_open"] == 1
    assert any(item["id"] == project_id for item in overview_data["projects"])
    assert any(item["id"] == task_in_custom["id"] for item in overview_data["upcoming_tasks"])

    # Teacher oversight & teacher read-only boundary.
    oversight = work_workspace.teacher_client.get(
        f"/api/work/teacher/oversight/projects/?class_id={work_workspace.section.pk}"
    )
    assert oversight.status_code == 200
    oversight_data = oversight.json()["data"]
    assert oversight_data["summary"]["total_projects"] == 1
    assert oversight_data["projects"][0]["project_id"] == project_id
    assert oversight_data["projects"][0]["progress"]["total_tasks"] == 1

    teacher_write = work_workspace.teacher_client.patch(
        f"/api/work/projects/{project_id}/",
        {"name": "Teacher Cannot Edit", "expected_version": unarchived.json()["data"]["version"]},
        format="json",
    )
    assert teacher_write.status_code == 403
    assert teacher_write.json()["error"]["code"] == "TEACHER_MUTATION_RESTRICTED"


def test_sprint_lifecycle_scope_changes_closure_snapshot_and_reports(
    work_workspace: WorkFixtureBundle,
):
    project = work_workspace.create_project(identifier="SPR1", name="Sprint Analytics Project")
    project_id = project["id"]
    done_state = State.objects.get(
        project_id=project_id, group="COMPLETED", deleted_at__isnull=True
    )

    task_done = work_workspace.create_task(project_id, title="Completed Story", story_points=5)
    task_removed = work_workspace.create_task(project_id, title="Deferred Story", story_points=3)
    task_rollover = work_workspace.create_task(project_id, title="Urgent Addition", story_points=2)

    today = date.today()
    sprint1_resp = work_workspace.leader_client.post(
        f"/api/work/projects/{project_id}/sprints/",
        {
            "name": "Sprint 1",
            "goal": "Initial goal",
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=14)).isoformat(),
        },
        format="json",
    )
    assert sprint1_resp.status_code == 201
    sprint1 = sprint1_resp.json()["data"]
    sprint1_id = sprint1["id"]

    sprint2_resp = work_workspace.leader_client.post(
        f"/api/work/projects/{project_id}/sprints/",
        {
            "name": "Sprint 2",
            "goal": "Rollover destination",
            "start_date": (today + timedelta(days=15)).isoformat(),
            "end_date": (today + timedelta(days=28)).isoformat(),
        },
        format="json",
    )
    assert sprint2_resp.status_code == 201
    sprint2_id = sprint2_resp.json()["data"]["id"]

    # List & update draft sprint.
    list_resp = work_workspace.leader_client.get(f"/api/work/projects/{project_id}/sprints/")
    assert list_resp.status_code == 200
    assert len(list_resp.json()["data"]) == 2

    patch_resp = work_workspace.leader_client.patch(
        f"/api/work/sprints/{sprint1_id}/",
        {"goal": "Deliver core auth & board", "expected_version": sprint1["version"]},
        format="json",
    )
    assert patch_resp.status_code == 200
    sprint1_ver = patch_resp.json()["data"]["version"]

    # Add tasks while sprint is DRAFT (no scope_change_reason required).
    add_draft = work_workspace.leader_client.post(
        f"/api/work/sprints/{sprint1_id}/tasks/",
        {
            "expected_version": sprint1_ver,
            "action": "ADD",
            "task_ids": [task_done["id"], task_removed["id"]],
        },
        format="json",
        **_idem_headers(),
    )
    assert add_draft.status_code == 200
    assert add_draft.json()["data"]["is_scope_creep"] is False
    sprint1_ver = add_draft.json()["data"]["version"]

    # Start sprint.
    started = work_workspace.leader_client.post(
        f"/api/work/projects/{project_id}/sprints/{sprint1_id}/start/",
        {"expected_version": sprint1_ver},
        format="json",
        **_idem_headers(),
    )
    assert started.status_code == 200
    assert started.json()["data"]["status"] == "ACTIVE"
    sprint1_ver = started.json()["data"]["version"]

    # Active scope change WITHOUT reason fails with 422.
    missing_reason = work_workspace.leader_client.post(
        f"/api/work/sprints/{sprint1_id}/tasks/",
        {
            "expected_version": sprint1_ver,
            "action": "ADD",
            "task_ids": [task_rollover["id"]],
        },
        format="json",
        **_idem_headers(),
    )
    assert missing_reason.status_code == 422
    assert missing_reason.json()["error"]["code"] == "SCOPE_CHANGE_REASON_REQUIRED"

    # Active scope ADD WITH reason succeeds & marks scope creep.
    add_active = work_workspace.leader_client.post(
        f"/api/work/sprints/{sprint1_id}/tasks/",
        {
            "expected_version": sprint1_ver,
            "action": "ADD",
            "task_ids": [task_rollover["id"]],
            "scope_change_reason": "Critical instructor requirement",
        },
        format="json",
        **_idem_headers(),
    )
    assert add_active.status_code == 200
    assert add_active.json()["data"]["is_scope_creep"] is True
    sprint1_ver = add_active.json()["data"]["version"]

    # Active scope REMOVE WITH reason records removal history.
    remove_active = work_workspace.leader_client.post(
        f"/api/work/sprints/{sprint1_id}/tasks/",
        {
            "expected_version": sprint1_ver,
            "action": "REMOVE",
            "task_ids": [task_removed["id"]],
            "scope_change_reason": "Deprioritized for next cycle",
        },
        format="json",
        **_idem_headers(),
    )
    assert remove_active.status_code == 200
    assert remove_active.json()["data"]["is_scope_creep"] is True
    sprint1_ver = remove_active.json()["data"]["version"]

    removed_history = SprintTask.objects.get(sprint_id=sprint1_id, task_id=task_removed["id"])
    assert removed_history.end_reason == "REMOVED"
    assert removed_history.removal_reason == "Deprioritized for next cycle"

    # Complete task_done inside the active sprint.
    transition = work_workspace.leader_client.patch(
        f"/api/work/tasks/{task_done['id']}/transition/",
        {"expected_version": task_done["version"], "target_state_id": str(done_state.pk)},
        format="json",
    )
    assert transition.status_code == 200

    # Live progress & burndown while ACTIVE.
    live_progress = work_workspace.leader_client.get(f"/api/work/sprints/{sprint1_id}/progress/")
    assert live_progress.status_code == 200
    assert live_progress.json()["data"]["snapshot_version"] is None
    assert live_progress.json()["data"]["totals"]["completed_work_item_count"] == 1
    assert live_progress.json()["data"]["totals"]["completed_estimate_points"] == 5

    live_burndown = work_workspace.leader_client.get(f"/api/work/sprints/{sprint1_id}/burndown/")
    assert live_burndown.status_code == 200
    assert live_burndown.json()["data"]["snapshot_version"] is None
    assert len(live_burndown.json()["data"]["days"]) >= 1

    # Close sprint with rollover into Sprint 2 and verify immutable closure snapshot.
    closed = work_workspace.leader_client.post(
        f"/api/work/sprints/{sprint1_id}/close/",
        {"expected_version": sprint1_ver, "target_sprint_id": sprint2_id},
        format="json",
        **_idem_headers(),
    )
    assert closed.status_code == 200
    close_data = closed.json()["data"]
    assert close_data["status"] == "COMPLETED"
    assert close_data["snapshot_version"] == 1
    assert close_data["target_sprint_id"] == sprint2_id
    assert close_data["summary"]["completed_work_item_count"] == 1
    assert close_data["summary"]["completed_estimate_points"] == 5
    assert close_data["summary"]["rolled_over_task_count"] == 1

    sprint_db = Sprint.objects.get(pk=sprint1_id)
    assert sprint_db.closure_snapshot is not None
    assert sprint_db.closure_snapshot["totals"]["completed_estimate_points"] == 5
    assert len(sprint_db.closure_snapshot["scope_history"]) == 3
    assert len(sprint_db.closure_snapshot["daily_burndown"]["days"]) >= 1

    assert SprintTask.objects.filter(
        sprint_id=sprint2_id,
        task_id=task_rollover["id"],
        scope_change_reason="ROLLOVER",
        ended_at__isnull=True,
    ).exists()

    # Post-closure reports read from immutable closure_snapshot.
    closed_progress = work_workspace.leader_client.get(f"/api/work/sprints/{sprint1_id}/progress/")
    assert closed_progress.status_code == 200
    assert closed_progress.json()["data"]["snapshot_version"] == 1
    assert closed_progress.json()["data"]["totals"]["completed_estimate_points"] == 5

    closed_burndown = work_workspace.leader_client.get(f"/api/work/sprints/{sprint1_id}/burndown/")
    assert closed_burndown.status_code == 200
    assert closed_burndown.json()["data"]["snapshot_version"] == 1
    assert len(closed_burndown.json()["data"]["days"]) >= 1


def test_task_crud_expand_subtasks_workflow_relations_metadata_lifecycle_and_deadlines(
    work_workspace: WorkFixtureBundle,
    monkeypatch: pytest.MonkeyPatch,
):
    storage_fake = InMemoryStorageFake()
    monkeypatch.setattr(
        "apps.collaboration.services.attachments.storage_client", lambda: storage_fake
    )

    project = work_workspace.create_project(identifier="TSK1", name="Task Workflow Project")
    project_id = project["id"]
    in_progress = State.objects.get(project_id=project_id, group="STARTED", deleted_at__isnull=True)

    # Labels CRUD.
    lbl1 = work_workspace.leader_client.post(
        f"/api/work/projects/{project_id}/labels/",
        {"name": "Backend", "color": "#2563EB", "description": "API tasks"},
        format="json",
    )
    assert lbl1.status_code == 201
    label1_id = lbl1.json()["data"]["id"]

    lbl2 = work_workspace.leader_client.post(
        f"/api/work/projects/{project_id}/labels/",
        {"name": "Temporary", "color": "#DC2626"},
        format="json",
    )
    assert lbl2.status_code == 201
    label2_id = lbl2.json()["data"]["id"]

    assert (
        work_workspace.leader_client.patch(
            f"/api/work/projects/{project_id}/labels/{label1_id}/",
            {"name": "Backend API"},
            format="json",
        ).status_code
        == 200
    )
    assert (
        work_workspace.leader_client.delete(
            f"/api/work/projects/{project_id}/labels/{label2_id}/"
        ).status_code
        == 200
    )

    # Epics CRUD.
    epic1 = work_workspace.leader_client.post(
        f"/api/work/projects/{project_id}/epics/",
        {
            "name": "Core Engine",
            "description": "Primary milestone",
            "lead_user_id": str(work_workspace.leader.pk),
            "status": "IN_PROGRESS",
        },
        format="json",
    )
    assert epic1.status_code == 201
    epic1_id = epic1.json()["data"]["id"]

    epic2 = work_workspace.leader_client.post(
        f"/api/work/projects/{project_id}/epics/",
        {"name": "Obsolete Epic"},
        format="json",
    )
    assert epic2.status_code == 201
    assert (
        work_workspace.leader_client.patch(
            f"/api/work/projects/{project_id}/epics/{epic1_id}/",
            {"status": "IN_PROGRESS", "description": "Updated milestone"},
            format="json",
        ).status_code
        == 200
    )
    assert (
        work_workspace.leader_client.delete(
            f"/api/work/projects/{project_id}/epics/{epic2.json()['data']['id']}/"
        ).status_code
        == 200
    )

    # Create root tasks A & B.
    today_vn = timezone.localdate(timezone=timezone.get_fixed_timezone(420))
    task_a = work_workspace.create_task(
        project_id,
        title="Build Auth Layer",
        description_html="<p>Initial <b>spec</b></p>",
        priority="HIGH",
        story_points=8,
        due_date=today_vn.isoformat(),
        epic_id=epic1_id,
        assignee_ids=[str(work_workspace.member.pk)],
    )
    assert task_a["code"] == "TSK1-1"
    task_a_id = task_a["id"]

    task_b = work_workspace.create_task(project_id, title="Build Reporting UI", priority="MEDIUM")
    task_b_id = task_b["id"]

    # Update task A & assign/remove label.
    updated_a = work_workspace.leader_client.patch(
        f"/api/work/tasks/{task_a_id}/",
        {
            "expected_version": task_a["version"],
            "title": "Build Core Auth Layer",
            "description_html": "<p>Clean <script>evil()</script><strong>spec</strong></p>",
        },
        format="json",
    )
    assert updated_a.status_code == 200
    assert "<script>" not in updated_a.json()["data"]["description_html"]
    task_a_ver = updated_a.json()["data"]["version"]

    lbl_add = work_workspace.leader_client.post(
        f"/api/work/tasks/{task_a_id}/labels/",
        {"expected_version": task_a_ver, "action": "ADD", "label_ids": [label1_id]},
        format="json",
    )
    assert lbl_add.status_code == 200
    assert lbl_add.json()["data"]["label_ids"] == [label1_id]
    task_a_ver = lbl_add.json()["data"]["version"]

    # Create subtask under task A.
    subtask_resp = work_workspace.leader_client.post(
        f"/api/work/tasks/{task_a_id}/subtasks/",
        {"title": "Write JWT verifier", "priority": "HIGH"},
        format="json",
        **_idem_headers(),
    )
    assert subtask_resp.status_code == 201
    subtask_id = subtask_resp.json()["data"]["id"]
    assert subtask_resp.json()["data"]["type"] == "SUBTASK"
    assert subtask_resp.json()["data"]["parent_id"] == task_a_id

    # Workflow: transition, block, unblock.
    trans = work_workspace.leader_client.patch(
        f"/api/work/tasks/{task_a_id}/transition/",
        {"expected_version": task_a_ver, "target_state_id": str(in_progress.pk)},
        format="json",
    )
    assert trans.status_code == 200
    assert trans.json()["data"]["state_id"] == str(in_progress.pk)
    task_a_ver = trans.json()["data"]["version"]

    blocked = work_workspace.leader_client.patch(
        f"/api/work/tasks/{task_a_id}/block/",
        {"expected_version": task_a_ver, "blocked_reason": "Waiting for schema signoff"},
        format="json",
    )
    assert blocked.status_code == 200
    assert blocked.json()["data"]["is_blocked"] is True
    task_a_ver = blocked.json()["data"]["version"]

    unblocked = work_workspace.leader_client.patch(
        f"/api/work/tasks/{task_a_id}/unblock/",
        {"expected_version": task_a_ver},
        format="json",
    )
    assert unblocked.status_code == 200
    assert unblocked.json()["data"]["is_blocked"] is False
    assert unblocked.json()["data"]["blocked_reason"] is None
    task_a_ver = unblocked.json()["data"]["version"]

    # Relations: BLOCKS + DAG cycle guard + RELATES_TO create/delete.
    blocks_rel = work_workspace.leader_client.post(
        f"/api/work/tasks/{task_a_id}/relations/",
        {"related_task_id": task_b_id, "relation_type": "BLOCKS"},
        format="json",
    )
    assert blocks_rel.status_code == 201

    cycle_rel = work_workspace.leader_client.post(
        f"/api/work/tasks/{task_b_id}/relations/",
        {"related_task_id": task_a_id, "relation_type": "BLOCKS"},
        format="json",
    )
    assert cycle_rel.status_code == 409
    assert cycle_rel.json()["error"]["code"] == "DAG_CYCLE_DETECTED"

    relates_rel = work_workspace.leader_client.post(
        f"/api/work/tasks/{task_a_id}/relations/",
        {"related_task_id": task_b_id, "relation_type": "RELATES_TO"},
        format="json",
    )
    assert relates_rel.status_code == 201
    relates_id = relates_rel.json()["data"]["id"]

    # Confirm an attachment on task A so expand=attachments returns real confirmed data.
    presign = work_workspace.leader_client.post(
        f"/api/work/tasks/{task_a_id}/attachments/presigned-url/",
        {"file_name": "design.txt", "file_size": 128, "content_type": "text/plain"},
        format="json",
    )
    assert presign.status_code == 200
    att_id = presign.json()["data"]["attachment_id"]
    att_row = Attachment.objects.get(pk=att_id)
    storage_fake.put_valid_object(att_row.storage_key, size=128, content_type="text/plain")
    confirm = work_workspace.leader_client.post(
        f"/api/work/tasks/{task_a_id}/attachments/",
        {"attachment_id": att_id},
        format="json",
        **_idem_headers(),
    )
    assert confirm.status_code == 200

    # Expand all detail relations on task A.
    expanded = work_workspace.member_client.get(
        f"/api/work/tasks/{task_a_id}/?expand=assignees,labels,subtasks,relations,attachments"
    )
    assert expanded.status_code == 200
    exp_data = expanded.json()["data"]
    assert exp_data["assignees"][0]["user_id"] == str(work_workspace.member.pk)
    assert exp_data["labels"][0]["id"] == label1_id
    assert [row["id"] for row in exp_data["subtasks"]] == [subtask_id]
    assert {row["relation_type"] for row in exp_data["relations"]} == {"BLOCKS", "RELATES_TO"}
    assert [row["id"] for row in exp_data["attachments"]] == [att_id]

    # Delete RELATES_TO relation and test task label REMOVE.
    assert (
        work_workspace.leader_client.delete(
            f"/api/work/tasks/{task_a_id}/relations/{relates_id}/"
        ).status_code
        == 200
    )
    task_a_ver_after_rel = Task.objects.get(pk=task_a_id).version
    lbl_remove = work_workspace.leader_client.post(
        f"/api/work/tasks/{task_a_id}/labels/",
        {"expected_version": task_a_ver_after_rel, "action": "REMOVE", "label_ids": [label1_id]},
        format="json",
    )
    assert lbl_remove.status_code == 200
    assert lbl_remove.json()["data"]["label_ids"] == []

    # Archive -> unarchive -> soft-delete -> restore on task B.
    task_b_ver = Task.objects.get(pk=task_b_id).version
    arch = work_workspace.leader_client.post(
        f"/api/work/tasks/{task_b_id}/archive/",
        {"expected_version": task_b_ver},
        format="json",
    )
    assert arch.status_code == 200
    assert arch.json()["data"]["archived_at"] is not None

    unarch = work_workspace.leader_client.post(
        f"/api/work/tasks/{task_b_id}/unarchive/",
        {"expected_version": arch.json()["data"]["version"]},
        format="json",
    )
    assert unarch.status_code == 200
    assert unarch.json()["data"]["archived_at"] is None

    soft_del = work_workspace.leader_client.delete(
        f"/api/work/tasks/{task_b_id}/",
        {"expected_version": unarch.json()["data"]["version"]},
        format="json",
    )
    assert soft_del.status_code == 200
    assert soft_del.json()["data"]["deleted_at"] is not None

    restored = work_workspace.leader_client.post(
        f"/api/work/tasks/{task_b_id}/restore/",
        {"expected_version": soft_del.json()["data"]["version"]},
        format="json",
    )
    assert restored.status_code == 200
    assert restored.json()["data"]["deleted_at"] is None

    # GET /api/work/me/tasks/ returns task A assigned to member.
    my_tasks = work_workspace.member_client.get("/api/work/me/tasks/?due_bucket=today")
    assert my_tasks.status_code == 200
    assert [row["id"] for row in my_tasks.json()["data"]] == [task_a_id]

    # Celery task scan_deadlines() emits task.deadline.reminder with producer="work-service".
    emitted_first = scan_deadlines()
    assert emitted_first >= 1
    reminder_events = list(
        OutboxEvent.objects.filter(
            producer=OutboxProducer.WORK,
            event_type="task.deadline.reminder",
            aggregate_id=task_a_id,
        )
    )
    assert len(reminder_events) == 1
    assert reminder_events[0].data["producer"] == "work-service"
    assert reminder_events[0].data["data"]["recipient_ids"] == [str(work_workspace.member.pk)]

    # Second scan in the same window is deduplicated by intent_id.
    assert scan_deadlines() == 0


def test_ai_proposal_bulk_apply_actions_idempotency_and_operation_lookup(
    work_workspace: WorkFixtureBundle,
    monkeypatch: pytest.MonkeyPatch,
):
    fake_ai = FakeAIProposalClient()
    monkeypatch.setattr("apps.tasks.services.ai_verification.ai_client", lambda: fake_ai)

    project = work_workspace.create_project(identifier="AI01", name="AI Proposal Project")
    project_id = project["id"]
    project_uuid = UUID(project_id)

    # Register BACKLOG proposal proof for 2 tasks with dependency ai-1 -> ai-2.
    fake_ai.register(
        VerifiedProposal(
            project_id=project_uuid,
            proposal_id="prop-backlog-1",
            kind="BACKLOG",
            context_version=project["version"],
            item_revisions={"ai-1": "rev-1", "ai-2": "rev-2"},
            actor_ids=frozenset({work_workspace.leader.pk}),
            expires_at=timezone.now() + timedelta(hours=1),
        )
    )
    backlog_key = str(uuid4())
    backlog_payload = {
        "proposal_id": "prop-backlog-1",
        "context_version": project["version"],
        "expected_project_version": project["version"],
        "tasks": [
            {
                "local_id": "ai-1",
                "ai_revision": "rev-1",
                "title": "Design schema",
                "priority": "HIGH",
                "story_points": 3,
            },
            {
                "local_id": "ai-2",
                "ai_revision": "rev-2",
                "title": "Implement API",
                "priority": "MEDIUM",
                "dependencies": ["ai-1"],
            },
        ],
    }
    apply_resp = work_workspace.leader_client.post(
        f"/api/work/projects/{project_id}/tasks/bulk-apply-ai/",
        backlog_payload,
        format="json",
        **_idem_headers(backlog_key),
    )
    assert apply_resp.status_code == 201, apply_resp.content
    apply_data = apply_resp.json()["data"]
    assert apply_data["created_count"] == 2
    assert apply_data["source"] == "AI_BACKLOG"
    operation_id = apply_data["operation_id"]
    created_ids = {item["local_id"]: item["id"] for item in apply_data["affected_tasks"]}

    # Idempotent replay returns exact same operation without invoking AI verifier again.
    calls_before_replay = len(fake_ai.calls)
    replay_resp = work_workspace.leader_client.post(
        f"/api/work/projects/{project_id}/tasks/bulk-apply-ai/",
        backlog_payload,
        format="json",
        **_idem_headers(backlog_key),
    )
    assert replay_resp.status_code == 201
    assert replay_resp.json()["data"]["operation_id"] == operation_id
    assert len(fake_ai.calls) == calls_before_replay
    assert Task.objects.filter(project_id=project_id, ai_proposal_id="prop-backlog-1").count() == 2

    # Operation lookup endpoint returns persisted receipt data.
    op_lookup = work_workspace.leader_client.get(
        f"/api/work/projects/{project_id}/ai-operations/{operation_id}/"
    )
    assert op_lookup.status_code == 200
    assert op_lookup.json()["data"]["operation_id"] == operation_id
    assert len(op_lookup.json()["data"]["affected_tasks"]) == 2

    # Subtask bulk-apply-ai under ai-1 parent task.
    parent_task = Task.objects.get(pk=created_ids["ai-1"])
    fake_ai.register(
        VerifiedProposal(
            project_id=project_uuid,
            proposal_id="prop-subtask-1",
            kind="SUBTASK",
            parent_id=parent_task.pk,
            context_version=parent_task.version,
            item_revisions={"sub-1": "srev-1"},
            actor_ids=frozenset({work_workspace.leader.pk}),
            expires_at=timezone.now() + timedelta(hours=1),
        )
    )
    sub_apply = work_workspace.leader_client.post(
        f"/api/work/tasks/{parent_task.pk}/subtasks/bulk-apply-ai/",
        {
            "proposal_id": "prop-subtask-1",
            "context_version": parent_task.version,
            "expected_parent_version": parent_task.version,
            "subtasks": [
                {
                    "local_id": "sub-1",
                    "ai_revision": "srev-1",
                    "title": "Draft DDL migration",
                }
            ],
        },
        format="json",
        **_idem_headers(),
    )
    assert sub_apply.status_code == 201, sub_apply.content
    assert sub_apply.json()["data"]["source"] == "AI_DECOMPOSED"
    assert sub_apply.json()["data"]["created_count"] == 1

    # AI Action apply (SET_PRIORITY + SET_DEADLINE) with idempotent replay & receipt lookup.
    target_task = Task.objects.get(pk=created_ids["ai-1"])
    new_due = (date.today() + timedelta(days=5)).isoformat()
    fake_ai.register(
        VerifiedProposal(
            project_id=project_uuid,
            proposal_id="prop-action-1",
            kind="ACTION",
            context_version=1,
            item_revisions={"act-item-1": "act-rev-1"},
            actor_ids=frozenset({work_workspace.leader.pk}),
            expires_at=timezone.now() + timedelta(hours=1),
            target_task_ids=frozenset({target_task.pk}),
        )
    )
    action_key = str(uuid4())
    action_payload = {
        "proposal_id": "prop-action-1",
        "item_id": "act-item-1",
        "ai_revision": "act-rev-1",
        "context_version": 1,
        "actions": [
            {
                "kind": "SET_PRIORITY",
                "task_id": str(target_task.pk),
                "expected_version": target_task.version,
                "priority": "URGENT",
            },
            {
                "kind": "SET_DEADLINE",
                "task_id": str(target_task.pk),
                "expected_version": target_task.version + 1,
                "due_date": new_due,
            },
        ],
    }
    action_resp = work_workspace.leader_client.post(
        f"/api/work/projects/{project_id}/ai-actions/apply/",
        action_payload,
        format="json",
        **_idem_headers(action_key),
    )
    assert action_resp.status_code == 200, action_resp.content
    action_data = action_resp.json()["data"]
    assert action_data["source"] == "AI_ACTION"

    target_task.refresh_from_db()
    assert target_task.priority == "URGENT"
    assert target_task.due_date.isoformat() == new_due

    # Replay action with same Idempotency-Key returns same receipt.
    action_replay = work_workspace.leader_client.post(
        f"/api/work/projects/{project_id}/ai-actions/apply/",
        action_payload,
        format="json",
        **_idem_headers(action_key),
    )
    assert action_replay.status_code == 200
    assert action_replay.json()["data"]["operation_id"] == action_data["operation_id"]

    action_op_lookup = work_workspace.leader_client.get(
        f"/api/work/projects/{project_id}/ai-operations/{action_data['operation_id']}/"
    )
    assert action_op_lookup.status_code == 200
    assert action_op_lookup.json()["data"]["proposal_id"] == "prop-action-1"


def test_collaboration_comments_mentions_teacher_feedback_attachments_and_activities(
    work_workspace: WorkFixtureBundle,
    monkeypatch: pytest.MonkeyPatch,
):
    storage_fake = InMemoryStorageFake()
    monkeypatch.setattr(
        "apps.collaboration.services.attachments.storage_client", lambda: storage_fake
    )
    monkeypatch.setattr("apps.collaboration.views.attachments.storage_client", lambda: storage_fake)

    project = work_workspace.create_project(identifier="COL1", name="Collaboration Project")
    project_id = project["id"]
    task = work_workspace.create_task(project_id, title="Review Architecture")
    task_id = task["id"]

    # Create comment with malicious HTML + @mention extraction.
    comment_resp = work_workspace.leader_client.post(
        "/api/work/comments/",
        {
            "task_id": task_id,
            "content_html": (
                "<p>Please check <script>alert('xss')</script>"
                f'<mention-component data-id="{work_workspace.member.pk}">@Binh</mention-component>'
                "</p>"
            ),
        },
        format="json",
    )
    assert comment_resp.status_code == 201, comment_resp.content
    comment = comment_resp.json()["data"]
    comment_id = comment["id"]
    assert "<script>" not in comment["content_html"]
    assert comment["is_teacher_feedback"] is False
    assert comment["mentioned_user_ids"] == [str(work_workspace.member.pk)]

    mention_event = OutboxEvent.objects.filter(
        producer=OutboxProducer.WORK,
        event_type="comment.mentions.added",
        aggregate_id=comment_id,
    ).first()
    assert mention_event is not None
    assert mention_event.data["data"]["recipient_ids"] == [str(work_workspace.member.pk)]

    # Edit & delete comment.
    edited = work_workspace.leader_client.patch(
        f"/api/work/comments/{comment_id}/",
        {"content_html": "<p>Updated <em>safe</em> comment</p>"},
        format="json",
    )
    assert edited.status_code == 200
    assert edited.json()["data"]["content_stripped"] == "Updated safe comment"

    deleted = work_workspace.leader_client.delete(f"/api/work/comments/{comment_id}/")
    assert deleted.status_code == 200
    assert deleted.json()["data"]["deleted_at"] is not None

    # Teacher feedback on project and on task emits teacher.feedback.added outbox events.
    proj_fb = work_workspace.teacher_client.post(
        "/api/work/comments/",
        {
            "project_id": project_id,
            "content_html": "<p>Good milestone progress overall.</p>",
        },
        format="json",
    )
    assert proj_fb.status_code == 201, proj_fb.content
    assert proj_fb.json()["data"]["is_teacher_feedback"] is True

    task_fb = work_workspace.teacher_client.post(
        "/api/work/comments/",
        {
            "task_id": task_id,
            "content_html": "<p>Add rollback coverage for edge cases.</p>",
        },
        format="json",
    )
    assert task_fb.status_code == 201, task_fb.content
    assert task_fb.json()["data"]["is_teacher_feedback"] is True

    feedback_events = OutboxEvent.objects.filter(
        producer=OutboxProducer.WORK,
        event_type="teacher.feedback.added",
        aggregate_id__in=[proj_fb.json()["data"]["id"], task_fb.json()["data"]["id"]],
    )
    assert feedback_events.count() == 2

    filtered_comments = work_workspace.member_client.get(
        f"/api/work/projects/{project_id}/comments/?is_teacher_feedback=true"
    )
    assert filtered_comments.status_code == 200
    assert len(filtered_comments.json()["data"]) == 1

    # Attachments presign -> confirm -> list -> download -> delete.
    presign = work_workspace.leader_client.post(
        f"/api/work/tasks/{task_id}/attachments/presigned-url/",
        {"file_name": "architecture.pdf", "file_size": 512, "content_type": "application/pdf"},
        format="json",
    )
    assert presign.status_code == 200
    att_id = presign.json()["data"]["attachment_id"]
    att_obj = Attachment.objects.get(pk=att_id)
    storage_fake.put_valid_object(att_obj.storage_key, size=512, content_type="application/pdf")

    confirmed = work_workspace.leader_client.post(
        f"/api/work/tasks/{task_id}/attachments/",
        {"attachment_id": att_id},
        format="json",
        **_idem_headers(),
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["status"] == "CONFIRMED"

    listed_att = work_workspace.member_client.get(f"/api/work/tasks/{task_id}/attachments/")
    assert listed_att.status_code == 200
    assert [row["id"] for row in listed_att.json()["data"]] == [att_id]

    download = work_workspace.member_client.get(
        f"/api/work/tasks/{task_id}/attachments/{att_id}/download/"
    )
    assert download.status_code == 200
    assert download.json()["data"]["download_url"].startswith("https://storage.local/download/")

    removed_att = work_workspace.leader_client.delete(
        f"/api/work/tasks/{task_id}/attachments/{att_id}/"
    )
    assert removed_att.status_code == 200
    assert removed_att.json()["data"]["deleted_at"] is not None

    # Project & task activity logs.
    proj_acts = work_workspace.leader_client.get(f"/api/work/projects/{project_id}/activities/")
    assert proj_acts.status_code == 200
    assert len(proj_acts.json()["data"]) >= 4
    assert any(row["actor_display_name"] == "Nguyen An" for row in proj_acts.json()["data"])

    task_acts = work_workspace.member_client.get(f"/api/work/tasks/{task_id}/activities/")
    assert task_acts.status_code == 200
    assert len(task_acts.json()["data"]) >= 3


def test_integrations_github_username_repo_connect_disconnect_receipt_consumer_and_task_links(
    work_workspace: WorkFixtureBundle,
    monkeypatch: pytest.MonkeyPatch,
    settings,
):
    settings.WORK_GITHUB_CONNECTION_ENABLED = True
    settings.WORK_SERVICE_KEYS = {"integration": [INTEGRATION_SERVICE_KEY]}
    settings.INTEGRATION_WORK_SERVICE_KEYS = []

    fake_integration = FakeIntegrationClient()
    monkeypatch.setattr(
        "apps.integrations.services.operations.integration_client", lambda: fake_integration
    )
    monkeypatch.setattr(
        "apps.integrations.services.links.integration_client", lambda: fake_integration
    )

    project = work_workspace.create_project(identifier="GH01", name="GitHub Sync Project")
    project_id = project["id"]
    task = work_workspace.create_task(project_id, title="Wire GitHub Webhooks")
    task_id = task["id"]
    task_code = task["code"]

    # Member GitHub username declare, update, blank rejection, and verification request.
    set_gh = work_workspace.member_client.patch(
        f"/api/work/projects/{project_id}/members/{work_workspace.member.pk}/github/",
        {"github_username": "binh-dev"},
        format="json",
    )
    assert set_gh.status_code == 200
    assert set_gh.json()["data"]["github_username"] == "binh-dev"
    assert set_gh.json()["data"]["is_github_verified"] is False

    upd_gh = work_workspace.member_client.patch(
        f"/api/work/projects/{project_id}/members/{work_workspace.member.pk}/github/",
        {"github_username": "binh-utask"},
        format="json",
    )
    assert upd_gh.status_code == 200
    assert upd_gh.json()["data"]["github_username"] == "binh-utask"

    blank_gh = work_workspace.member_client.patch(
        f"/api/work/projects/{project_id}/members/{work_workspace.member.pk}/github/",
        {"github_username": ""},
        format="json",
    )
    assert blank_gh.status_code == 400

    req_ver = work_workspace.leader_client.post(
        f"/api/work/projects/{project_id}/members/{work_workspace.member.pk}/github/request-verification/",
        {},
        format="json",
        **_idem_headers(),
    )
    assert req_ver.status_code == 200

    # Consume integration.github.account.changed (verify then clear verification).
    consumer = FakeKafkaConsumer()
    dlq = FakeDLQPublisher()

    def _emit_integration_record(
        event_type: str,
        aggregate_id: str,
        payload: dict[str, Any],
        event_id: str | None = None,
    ):
        envelope = {
            "event_id": event_id or str(uuid4()),
            "event_type": event_type,
            "event_version": 1,
            "aggregate_id": aggregate_id,
            "occurred_at": timezone.now().isoformat(),
            "trace_id": str(uuid4()),
            "producer": "integration-service",
            "payload": payload,
        }
        record = FakeKafkaRecord(json.dumps(envelope).encode("utf-8"))
        process_integration_record(record, consumer, dlq=dlq)
        return envelope["event_id"], record

    verify_event_id, _ = _emit_integration_record(
        "integration.github.account.changed",
        str(work_workspace.member.pk),
        {
            "user_id": str(work_workspace.member.pk),
            "github_user_id": "99001",
            "github_username": "binh-utask",
            "source_version": 1,
            "verified": True,
            "synced_at": timezone.now().isoformat(),
        },
    )
    member_row = ProjectMember.objects.get(project_id=project_id, user_id=work_workspace.member.pk)
    assert member_row.is_github_verified is True
    assert member_row.github_user_id == "99001"
    assert ConsumedEvent.objects.filter(
        event_id=verify_event_id, consumer_group=settings.WORK_INTEGRATION_KAFKA_GROUP
    ).exists()

    # Clear verification via newer integration.github.account.changed(verified=False).
    _emit_integration_record(
        "integration.github.account.changed",
        str(work_workspace.member.pk),
        {
            "user_id": str(work_workspace.member.pk),
            "github_user_id": "99001",
            "github_username": "binh-utask",
            "source_version": 2,
            "verified": False,
            "synced_at": timezone.now().isoformat(),
        },
    )
    member_row.refresh_from_db()
    assert member_row.is_github_verified is False

    # Repository connect request -> 202 PENDING + internal receipt lookup.
    connect_op = "op-connect-001"
    connect_resp = work_workspace.leader_client.post(
        f"/api/work/projects/{project_id}/github/repository/",
        {
            "github_repo_id": "777123",
            "operation_id": connect_op,
            "expected_connection_generation": 0,
        },
        format="json",
        **_idem_headers(),
    )
    assert connect_resp.status_code == 202, connect_resp.content
    assert connect_resp.json()["data"]["status"] == "PENDING"
    assert connect_resp.json()["data"]["connection_generation"] == 1

    internal_client = APIClient()
    receipt_resp = internal_client.get(
        f"/api/v1/internal/integration/projects/{project_id}/github/operations/{connect_op}",
        HTTP_X_SERVICE_KEY=INTEGRATION_SERVICE_KEY,
    )
    assert receipt_resp.status_code == 200, receipt_resp.content
    assert receipt_resp["Cache-Control"] == "no-store"
    assert receipt_resp.json()["data"]["applied"] is True
    assert receipt_resp.json()["data"]["status"] == "PENDING"
    assert receipt_resp.json()["data"]["repo_id"] == "777123"

    # Deliver CONNECTED event via Kafka consumer + verify durable core_consumed_events dedupe.
    conn_payload = {
        "project_id": project_id,
        "operation_id": connect_op,
        "generation": 1,
        "source_version": fake_integration.version + 1,
        "status": "CONNECTED",
        "repo_id": "777123",
        "repo_owner": "utask-org",
        "repo_name": "capstone-repo",
        "default_branch": "main",
        "synced_at": timezone.now().isoformat(),
    }
    conn_event_id, conn_record = _emit_integration_record(
        "integration.project.connection.changed",
        project_id,
        conn_payload,
    )
    project_row = Project.objects.get(pk=project_id)
    assert project_row.github_connection_status == "CONNECTED"
    assert project_row.github_repo_id == "777123"
    assert ConsumedEvent.objects.filter(
        event_id=conn_event_id, consumer_group=settings.WORK_INTEGRATION_KAFKA_GROUP
    ).exists()

    # Exact duplicate Kafka record is deduplicated cleanly (no DLQ, no version bump).
    version_before_dup = project_row.version
    process_integration_record(conn_record, consumer, dlq=dlq)
    project_row.refresh_from_db()
    assert project_row.version == version_before_dup
    assert len(dlq.entries) == 0

    # Reusing same event_id with altered payload routes to DLQ.
    _emit_integration_record(
        "integration.project.connection.changed",
        project_id,
        {**conn_payload, "default_branch": "develop"},
        event_id=conn_event_id,
    )
    assert len(dlq.entries) == 1

    # Ingest candidate reference event -> confirm link -> manual link -> delete link.
    _emit_integration_record(
        "integration.github.reference.detected",
        project_id,
        {
            "project_id": project_id,
            "repo_id": "777123",
            "generation": 1,
            "source_version": 1,
            "task_code": task_code,
            "link_type": "BRANCH",
            "ref_id": "feat/gh-webhooks",
            "title": "feat/gh-webhooks",
            "status": None,
            "url": "https://github.com/utask-org/capstone-repo/tree/feat/gh-webhooks",
            "is_verified": True,
            "synced_at": timezone.now().isoformat(),
        },
    )
    candidate = TaskGitHubLink.objects.get(task_id=task_id, link_type="BRANCH")
    assert candidate.confirmation_status == "PENDING"

    confirmed_link = work_workspace.leader_client.post(
        f"/api/work/tasks/{task_id}/github-links/{candidate.pk}/confirm/",
        {},
        format="json",
        **_idem_headers(),
    )
    assert confirmed_link.status_code == 200
    assert confirmed_link.json()["data"]["confirmation_status"] == "CONFIRMED"

    fake_integration.register_reference(
        ReferenceFact(
            project_id=UUID(project_id),
            repo_id="777123",
            generation=1,
            source_version=2,
            link_type="PULL_REQUEST",
            ref_id="42",
            title="Implement webhooks",
            status="OPEN",
            url="https://github.com/utask-org/capstone-repo/pull/42",
            is_verified=True,
            synced_at=timezone.now(),
        )
    )
    manual_pr = work_workspace.member_client.post(
        f"/api/work/tasks/{task_id}/github-links/",
        {"link_type": "PULL_REQUEST", "github_ref_id": "#42"},
        format="json",
        **_idem_headers(),
    )
    assert manual_pr.status_code == 201, manual_pr.content
    pr_link_id = manual_pr.json()["data"]["id"]
    assert manual_pr.json()["data"]["github_ref_id"] == "42"
    assert manual_pr.json()["data"]["confirmation_status"] == "CONFIRMED"

    unlink_resp = work_workspace.member_client.delete(
        f"/api/work/tasks/{task_id}/github-links/{pr_link_id}/"
    )
    assert unlink_resp.status_code == 200
    assert unlink_resp.json()["data"]["unlinked_id"] == pr_link_id

    # Disconnect repository -> receipt shows repo_id=None -> deliver DISCONNECTED event.
    disc_op = "op-disconnect-001"
    disc_resp = work_workspace.leader_client.delete(
        f"/api/work/projects/{project_id}/github/repository/",
        {"operation_id": disc_op, "expected_connection_generation": 1},
        format="json",
        **_idem_headers(),
    )
    assert disc_resp.status_code == 202, disc_resp.content

    disc_receipt = internal_client.get(
        f"/api/v1/internal/integration/projects/{project_id}/github/operations/{disc_op}",
        HTTP_X_SERVICE_KEY=INTEGRATION_SERVICE_KEY,
    )
    assert disc_receipt.status_code == 200
    assert disc_receipt.json()["data"]["repo_id"] is None
    assert disc_receipt.json()["data"]["generation"] == 2

    _emit_integration_record(
        "integration.project.connection.changed",
        project_id,
        {
            "project_id": project_id,
            "operation_id": disc_op,
            "generation": 2,
            "source_version": fake_integration.version + 1,
            "status": "DISCONNECTED",
            "repo_id": None,
            "repo_owner": None,
            "repo_name": None,
            "default_branch": None,
            "synced_at": timezone.now().isoformat(),
        },
    )
    project_row.refresh_from_db()
    assert project_row.github_connection_status == "DISCONNECTED"
    assert project_row.github_repo_id is None


def test_postgresql_write_guards_enforce_immutability(work_workspace: WorkFixtureBundle):
    project = work_workspace.create_project(identifier="GRD1", name="Write Guards Project")
    project_id = project["id"]
    task = work_workspace.create_task(project_id, title="Guard Check Task")
    task_id = task["id"]

    # 1. work_activity_immutable blocks UPDATE and DELETE on work_activities.
    activity = WorkActivity.objects.filter(scope_project_id=project_id).first()
    assert activity is not None
    with pytest.raises(IntegrityError, match="Activity is append only"):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE work_activities SET verb = 'tampered' WHERE id = %s",
                    [activity.pk],
                )

    with pytest.raises(IntegrityError, match="Activity is append only"):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM work_activities WHERE id = %s", [activity.pk])

    # 2. work_sprint_guard blocks mutating a closed sprint; scope guard blocks deleting scope rows.
    today = date.today()
    sprint = work_workspace.leader_client.post(
        f"/api/work/projects/{project_id}/sprints/",
        {
            "name": "Closed Sprint",
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=7)).isoformat(),
        },
        format="json",
    ).json()["data"]
    sprint_id = sprint["id"]

    added = work_workspace.leader_client.post(
        f"/api/work/sprints/{sprint_id}/tasks/",
        {"expected_version": sprint["version"], "action": "ADD", "task_ids": [task_id]},
        format="json",
        **_idem_headers(),
    ).json()["data"]
    started = work_workspace.leader_client.post(
        f"/api/work/projects/{project_id}/sprints/{sprint_id}/start/",
        {"expected_version": added["version"]},
        format="json",
        **_idem_headers(),
    ).json()["data"]
    close_resp = work_workspace.leader_client.post(
        f"/api/work/sprints/{sprint_id}/close/",
        {"expected_version": started["version"]},
        format="json",
        **_idem_headers(),
    )
    assert close_resp.status_code == 200

    with pytest.raises(IntegrityError, match="Immutable closed Sprint"):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE sprints SET name = 'Tampered Sprint' WHERE id = %s",
                    [sprint_id],
                )

    scope_row = SprintTask.objects.get(sprint_id=sprint_id, task_id=task_id)
    with pytest.raises(IntegrityError, match="Scope history cannot be deleted"):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM sprint_tasks WHERE id = %s", [scope_row.pk])

    # 3. work_collaboration_guard blocks changing comment author or feedback flag.
    comment_resp = work_workspace.leader_client.post(
        "/api/work/comments/",
        {"task_id": task_id, "content_html": "<p>Original author comment</p>"},
        format="json",
    )
    assert comment_resp.status_code == 201
    comment_id = comment_resp.json()["data"]["id"]
    assert Comment.objects.filter(pk=comment_id).exists()

    with pytest.raises(IntegrityError, match="Immutable author"):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE comments SET user_id = %s WHERE id = %s",
                    [work_workspace.member.pk, comment_id],
                )

    with pytest.raises(IntegrityError, match="Immutable author"):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE comments SET is_teacher_feedback = TRUE WHERE id = %s",
                    [comment_id],
                )
