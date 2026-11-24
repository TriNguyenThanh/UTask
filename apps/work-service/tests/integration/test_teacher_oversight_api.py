from datetime import UTC, datetime, timedelta

import pytest
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.messaging.models import Activity
from apps.projects.models import Project, ProjectMember, State
from apps.sprints.models import Sprint, SprintTask
from apps.tasks.models import Task, TaskAssignment
from common.errors import WorkError

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _make_project(
    identifier, group_id, class_id, actor_id, *, last_activity_at=None, archived_at=None
):
    project = Project.objects.create(
        identifier=identifier,
        name=f"Dự án {identifier}",
        classroom_group_id=group_id,
        class_id=class_id,
        last_activity_at=last_activity_at,
        archived_at=archived_at,
    )
    ProjectMember.objects.create(
        project=project, user_id=actor_id, role="LEADER", status="ACTIVE", joined_at=timezone.now()
    )
    todo = State.objects.create(
        project=project,
        name="Cần làm",
        slug="todo",
        color="#2563EB",
        sequence=10000,
        group="UNSTARTED",
        is_default=True,
    )
    done = State.objects.create(
        project=project,
        name="Hoàn thành",
        slug="done",
        color="#16A34A",
        sequence=20000,
        group="COMPLETED",
    )
    return project, todo, done


def test_teacher_oversight_signals_scope_intersection_and_fail_closed(
    classroom, actors, client_for, monkeypatch
):
    fixed_now = datetime(2026, 12, 10, 4, 0, tzinfo=UTC)  # 2026-12-10 ICT
    monkeypatch.setattr("apps.projects.queries.oversight.timezone.now", lambda: fixed_now)
    today = fixed_now.date()

    p1, p1_todo, p1_done = _make_project(
        "OV1",
        "group-1",
        "class-1",
        actors["leader"],
        last_activity_at=fixed_now - timedelta(days=10),
    )
    p2, p2_todo, p2_done = _make_project(
        "OV2",
        "group-2",
        "class-2",
        actors["leader"],
        last_activity_at=fixed_now - timedelta(days=1),
    )
    p_archived, _, _ = _make_project(
        "OVA",
        "group-a",
        "class-1",
        actors["leader"],
        last_activity_at=fixed_now - timedelta(days=20),
        archived_at=fixed_now - timedelta(days=2),
    )
    _make_project(
        "FOR",
        "group-foreign",
        "class-foreign",
        actors["outsider"],
        last_activity_at=fixed_now - timedelta(days=30),
    )

    classroom.teachers[actors["teacher"]] = ["group-1", "group-2", "group-a"]

    # p1 triggers OVERDUE_TASKS, BLOCKED_TASKS, NO_RECENT_ACTIVITY, BEHIND_SPRINT_SCHEDULE
    t1 = Task.objects.create(
        project=p1,
        state=p1_todo,
        sequence_id=1,
        title="Quá hạn và bị chặn",
        story_points=5,
        due_date=today - timedelta(days=2),
        is_blocked=True,
        blocked_reason="Thiếu môi trường",
        created_by_user_id=actors["leader"],
    )
    t2 = Task.objects.create(
        project=p1,
        state=p1_todo,
        sequence_id=2,
        title="Chưa giao",
        story_points=3,
        created_by_user_id=actors["leader"],
    )
    TaskAssignment.objects.create(task=t1, user_id=actors["leader"])
    sprint = Sprint.objects.create(
        project=p1,
        name="Sprint 1",
        status="ACTIVE",
        start_date=today - timedelta(days=9),
        end_date=today + timedelta(days=1),
        started_at=fixed_now - timedelta(days=9),
    )
    SprintTask.objects.create(
        sprint=sprint,
        task=t1,
        added_at=fixed_now - timedelta(days=9),
        scope_change_reason="Phạm vi đầu chu kỳ",
    )
    SprintTask.objects.create(
        sprint=sprint,
        task=t2,
        added_at=fixed_now - timedelta(days=9),
        scope_change_reason="Phạm vi đầu chu kỳ",
    )

    # p2 is healthy (100% done, recent activity)
    t_done = Task.objects.create(
        project=p2,
        state=p2_done,
        sequence_id=1,
        title="Đã xong",
        story_points=8,
        completed_at=fixed_now - timedelta(days=1),
        created_by_user_id=actors["leader"],
    )
    TaskAssignment.objects.create(task=t_done, user_id=actors["leader"])

    teacher = client_for(actors["teacher"])

    with CaptureQueriesContext(connection) as queries:
        reply = teacher.get("/teacher/oversight/projects/")
    assert reply.status_code == 200, reply.content
    assert len(queries) <= 6
    data = reply.json()["data"]
    assert {p["classroom_group_id"] for p in data["projects"]} == {"group-1", "group-2"}
    assert data["summary"]["total_projects"] == 2
    assert data["summary"]["projects_with_signals"] == 1
    assert data["summary"]["inactive_projects"] == 1
    assert data["summary"]["total_overdue_tasks"] == 1
    assert data["summary"]["total_blocked_tasks"] == 1
    assert data["summary"]["average_completion_rate"] == 50.0

    by_group = {p["classroom_group_id"]: p for p in data["projects"]}
    ov1 = by_group["group-1"]
    assert ov1["progress"] == {
        "total_tasks": 2,
        "completed_tasks": 0,
        "completion_rate": 0.0,
        "total_points": 8,
        "completed_points": 0,
    }
    assert ov1["overdue_count"] == 1
    assert ov1["blocked_count"] == 1
    assert ov1["unassigned_count"] == 1
    assert ov1["active_sprint"]["total_tasks"] == 2
    assert {s["code"] for s in ov1["signals"]} == {
        "OVERDUE_TASKS",
        "BLOCKED_TASKS",
        "NO_RECENT_ACTIVITY",
        "BEHIND_SPRINT_SCHEDULE",
    }
    assert by_group["group-2"]["signals"] == []

    # Foreign group requested by caller MUST be stripped by intersection
    filtered = teacher.get(
        "/teacher/oversight/projects/",
        {"classroom_group_ids": "group-1,group-foreign"},
    )
    assert filtered.status_code == 200
    assert [p["classroom_group_id"] for p in filtered.json()["data"]["projects"]] == ["group-1"]

    # Class filter & include_archived
    by_class = teacher.get(
        "/teacher/oversight/projects/",
        {"class_id": "class-1", "include_archived": "true"},
    )
    assert by_class.status_code == 200
    assert {p["project_id"] for p in by_class.json()["data"]["projects"]} == {
        str(p1.pk),
        str(p_archived.pk),
    }

    # Validation guards
    too_many = ",".join(f"g-{i}" for i in range(101))
    assert (
        teacher.get("/teacher/oversight/projects/", {"classroom_group_ids": too_many}).status_code
        == 400
    )
    assert teacher.get("/teacher/oversight/projects/", {"inactive_days": 0}).status_code == 400
    assert teacher.get("/teacher/oversight/projects/", {"inactive_days": 91}).status_code == 400

    # Fail-closed when Classroom is unavailable
    def fail_classroom(self, actor):
        raise WorkError("CLASSROOM_UNAVAILABLE", "Dịch vụ lớp học hiện không khả dụng.", 503)

    monkeypatch.setattr(classroom, "teacher_group_ids", fail_classroom)
    outage = teacher.get("/teacher/oversight/projects/")
    assert outage.status_code == 503
    assert outage.json()["error"]["code"] == "CLASSROOM_UNAVAILABLE"


def test_record_activities_populates_scope_project_and_last_activity_at(
    task_api, client_for, actors
):
    leader, _, create = task_api
    task = create(title="Công việc kiểm thử nhật ký")
    project = Project.objects.get(pk=task["project_id"])
    assert project.last_activity_at is not None

    member = client_for(actors["member"])
    comment_reply = member.post(
        "/comments/",
        {"task_id": task["id"], "content_html": "<p>Trao đổi</p>"},
        format="json",
    )
    assert comment_reply.status_code == 201
    comment_id = comment_reply.json()["data"]["id"]
    assert (
        member.patch(
            f"/comments/{comment_id}/",
            {"content_html": "<p>Trao đổi đã sửa</p>"},
            format="json",
        ).status_code
        == 200
    )

    activities = list(Activity.objects.all())
    assert len(activities) >= 3
    assert all(row.scope_project_id == project.pk for row in activities)
    latest_activity = Activity.objects.order_by("-created_at").first().created_at
    project.refresh_from_db()
    assert project.last_activity_at >= latest_activity

    # Append-only trigger remains enforced after migration 0010
    with pytest.raises(IntegrityError), transaction.atomic():
        Activity.objects.filter(pk=activities[0].pk).update(verb="tampered")


def test_teacher_oversight_severities_repeated_params_archived_and_empty_scope(
    classroom, actors, client_for, monkeypatch
):
    fixed_now = datetime(2026, 12, 15, 4, 0, tzinfo=UTC)
    monkeypatch.setattr("apps.projects.queries.oversight.timezone.now", lambda: fixed_now)
    today = fixed_now.date()

    # p_high: 3 overdue, 2 blocked, 16d inactive, sprint past end_date (all HIGH)
    p_high, ph_todo, _ = _make_project(
        "HI1",
        "g-high",
        "c-1",
        actors["leader"],
        last_activity_at=fixed_now - timedelta(days=16),
    )
    for i in range(1, 4):
        Task.objects.create(
            project=p_high,
            state=ph_todo,
            sequence_id=i,
            title=f"High {i}",
            due_date=today - timedelta(days=i),
            is_blocked=(i <= 2),
            blocked_reason="Chặn" if i <= 2 else None,
            created_by_user_id=actors["leader"],
        )
    past_sprint = Sprint.objects.create(
        project=p_high,
        name="Sprint Quá Hạn",
        status="ACTIVE",
        start_date=today - timedelta(days=10),
        end_date=today - timedelta(days=1),
        started_at=fixed_now - timedelta(days=10),
    )
    SprintTask.objects.create(
        sprint=past_sprint,
        task=Task.objects.get(project=p_high, sequence_id=1),
        added_at=fixed_now - timedelta(days=10),
        scope_change_reason="Phạm vi",
    )

    # p_med: mid-sprint lag (60% elapsed, 25% done -> MEDIUM) & created_at fallback
    with monkeypatch.context() as mp:
        mp.setattr("django.utils.timezone.now", lambda: fixed_now - timedelta(days=8))
        p_med, pm_todo, pm_done = _make_project(
            "MD1",
            "g-med",
            "c-1",
            actors["leader"],
            last_activity_at=None,
        )
    mid_sprint = Sprint.objects.create(
        project=p_med,
        name="Sprint Giữa Kỳ",
        status="ACTIVE",
        start_date=today - timedelta(days=5),
        end_date=today + timedelta(days=4),  # 10 days total, 6 elapsed = 0.60
        started_at=fixed_now - timedelta(days=5),
    )
    for i in range(1, 5):
        t = Task.objects.create(
            project=p_med,
            state=pm_done if i == 1 else pm_todo,
            sequence_id=i,
            title=f"Mid {i}",
            completed_at=fixed_now if i == 1 else None,
            created_by_user_id=actors["leader"],
        )
        SprintTask.objects.create(
            sprint=mid_sprint,
            task=t,
            added_at=fixed_now - timedelta(days=5),
            scope_change_reason="Phạm vi",
        )

    # p_empty: 0 tasks (completion_rate=None), recent activity
    p_empty, _, _ = _make_project(
        "EM1",
        "g-empty",
        "c-2",
        actors["leader"],
        last_activity_at=fixed_now - timedelta(days=1),
    )

    # p_arch: archived project MUST NOT emit NO_RECENT_ACTIVITY or BEHIND_SPRINT_SCHEDULE
    p_arch, pa_todo, _ = _make_project(
        "AR1",
        "g-arch",
        "c-2",
        actors["leader"],
        last_activity_at=fixed_now - timedelta(days=30),
        archived_at=fixed_now - timedelta(days=5),
    )
    arch_sprint = Sprint.objects.create(
        project=p_arch,
        name="Sprint Archived",
        status="ACTIVE",
        start_date=today - timedelta(days=20),
        end_date=today - timedelta(days=10),
        started_at=fixed_now - timedelta(days=20),
    )
    t_arch = Task.objects.create(
        project=p_arch,
        state=pa_todo,
        sequence_id=1,
        title="Task archived project",
        created_by_user_id=actors["leader"],
    )
    SprintTask.objects.create(
        sprint=arch_sprint,
        task=t_arch,
        added_at=fixed_now - timedelta(days=20),
        scope_change_reason="Phạm vi",
    )

    classroom.teachers[actors["teacher"]] = ["g-high", "g-med", "g-empty", "g-arch"]
    teacher = client_for(actors["teacher"])

    # Repeated query params (?classroom_group_ids=g-high&classroom_group_ids=g-med)
    repeated = teacher.get(
        "/teacher/oversight/projects/?classroom_group_ids=g-high&classroom_group_ids=g-med"
    )
    assert repeated.status_code == 200, repeated.content
    by_id = {row["project_id"]: row for row in repeated.json()["data"]["projects"]}
    assert set(by_id) == {str(p_high.pk), str(p_med.pk)}
    high_sigs = {s["code"]: s["severity"] for s in by_id[str(p_high.pk)]["signals"]}
    assert high_sigs == {
        "OVERDUE_TASKS": "HIGH",
        "BLOCKED_TASKS": "HIGH",
        "NO_RECENT_ACTIVITY": "HIGH",
        "BEHIND_SPRINT_SCHEDULE": "HIGH",
    }
    med_sigs = {s["code"]: s["severity"] for s in by_id[str(p_med.pk)]["signals"]}
    assert med_sigs == {
        "NO_RECENT_ACTIVITY": "MEDIUM",
        "BEHIND_SPRINT_SCHEDULE": "MEDIUM",
    }

    # Empty project (0 tasks) & archived project (no inactivity/sprint signals)
    c2 = teacher.get(
        "/teacher/oversight/projects/", {"class_id": "c-2", "include_archived": "true"}
    )
    assert c2.status_code == 200
    c2_data = c2.json()["data"]
    c2_by_id = {row["project_id"]: row for row in c2_data["projects"]}
    assert c2_by_id[str(p_empty.pk)]["progress"]["completion_rate"] is None
    assert c2_by_id[str(p_empty.pk)]["signals"] == []
    assert c2_by_id[str(p_arch.pk)]["signals"] == []

    # Invalid empty item inside classroom_group_ids -> 400
    assert (
        teacher.get(
            "/teacher/oversight/projects/", {"classroom_group_ids": "g-high,,g-med"}
        ).status_code
        == 400
    )

    # Empty effective scope (teacher asks for foreign group only, or student with no teacher groups)
    only_foreign = teacher.get("/teacher/oversight/projects/", {"classroom_group_ids": "not-mine"})
    assert only_foreign.status_code == 200
    assert only_foreign.json()["data"]["projects"] == []
    assert only_foreign.json()["data"]["summary"]["average_completion_rate"] is None

    student_res = client_for(actors["member"]).get("/teacher/oversight/projects/")
    assert student_res.status_code == 200
    assert student_res.json()["data"]["projects"] == []


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_migration_0010_backfills_all_8_activity_subjects_and_last_activity_at(actors):
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    pre_target = [
        ("projects", "0002_multiple_group_projects"),
        ("messaging", "0009_activity_sprint_activity_chk_activity_subject"),
    ]

    try:
        executor.migrate(pre_target)
        apps_before = MigrationExecutor(connection).loader.project_state(pre_target).apps
        ProjectBefore = apps_before.get_model("projects", "Project")
        MemberBefore = apps_before.get_model("projects", "ProjectMember")
        StateBefore = apps_before.get_model("projects", "State")
        TaskBefore = apps_before.get_model("tasks", "Task")
        EpicBefore = apps_before.get_model("tasks", "Epic")
        LabelBefore = apps_before.get_model("tasks", "Label")
        CommentBefore = apps_before.get_model("collaboration", "Comment")
        SprintBefore = apps_before.get_model("sprints", "Sprint")
        ActivityBefore = apps_before.get_model("messaging", "Activity")

        now = timezone.now()
        proj_a = ProjectBefore.objects.create(
            identifier="BFA", name="Backfill A", classroom_group_id="bf-group-a"
        )
        proj_b = ProjectBefore.objects.create(
            identifier="BFB", name="Backfill B", classroom_group_id="bf-group-b"
        )
        member = MemberBefore.objects.create(
            project=proj_a, user_id=actors["leader"], role="LEADER", status="ACTIVE", joined_at=now
        )
        state = StateBefore.objects.create(
            project=proj_a,
            name="Todo",
            slug="todo",
            color="#111111",
            sequence=10000,
            group="UNSTARTED",
            is_default=True,
        )
        epic = EpicBefore.objects.create(project=proj_a, name="Epic BF")
        label = LabelBefore.objects.create(project=proj_a, name="Lbl BF", color="#222222")
        task = TaskBefore.objects.create(
            project=proj_a,
            state=state,
            sequence_id=1,
            title="Task BF",
            created_by_user_id=actors["leader"],
        )
        project_comment = CommentBefore.objects.create(
            project=proj_a,
            user_id=actors["leader"],
            content_html="<p>p</p>",
            content_stripped="p",
        )
        task_comment = CommentBefore.objects.create(
            task=task,
            user_id=actors["leader"],
            content_html="<p>t</p>",
            content_stripped="t",
        )
        sprint = SprintBefore.objects.create(project=proj_a, name="Sprint BF")

        subject_kwargs = [
            {"project": proj_a},
            {"project_member": member},
            {"state": state},
            {"task": task},
            {"epic": epic},
            {"label": label},
            {"comment": project_comment},
            {"comment": task_comment},
            {"sprint": sprint},
        ]
        created_ids = []
        for idx, kwargs in enumerate(subject_kwargs):
            row = ActivityBefore.objects.create(
                actor_user_id=actors["leader"], verb=f"v{idx}", **kwargs
            )
            created_ids.append(row.pk)

        # Run forward migration 0003 + 0010 on populated tables
        MigrationExecutor(connection).migrate(latest)

        backfilled = list(Activity.objects.filter(pk__in=created_ids))
        assert len(backfilled) == 9
        assert all(row.scope_project_id == proj_a.pk for row in backfilled)
        expected_latest = max(row.created_at for row in backfilled)
        assert Project.objects.get(pk=proj_a.pk).last_activity_at == expected_latest
        assert Project.objects.get(pk=proj_b.pk).last_activity_at is None

        # Trigger work_activity_immutable MUST remain re-enabled after migration 0010
        with pytest.raises(IntegrityError), transaction.atomic():
            Activity.objects.filter(pk=created_ids[0]).update(verb="tampered")
    finally:
        MigrationExecutor(connection).migrate(latest)
