from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.projects.models import Project, ProjectMember, State
from apps.sprints.models import Sprint, SprintTask
from apps.tasks.models import Label, Task, TaskAssignment, TaskLabel
from tests.fixtures.classroom import GroupMemberFact, GroupSnapshot

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _seed_project(classroom, actors, *, identifier, group_id, class_id, member_status="ACTIVE"):
    project = Project.objects.create(
        identifier=identifier,
        name=f"Dự án {identifier}",
        classroom_group_id=group_id,
        class_id=class_id,
    )
    now = timezone.now()
    ProjectMember.objects.create(
        project=project, user_id=actors["leader"], role="LEADER", status="ACTIVE", joined_at=now
    )
    ProjectMember.objects.create(
        project=project,
        user_id=actors["member"],
        role="MEMBER",
        status=member_status,
        joined_at=now,
        left_at=None if member_status == "ACTIVE" else now,
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
    classroom.groups[group_id] = GroupSnapshot(
        group_id,
        class_id,
        1,
        (GroupMemberFact(actors["leader"], "LEADER"), GroupMemberFact(actors["member"], "MEMBER")),
    )
    return project, todo, done


def test_my_tasks_filters_ordering_cursor_and_scope(classroom, actors, client_for, monkeypatch):
    fixed_now = datetime(2026, 12, 2, 3, 0, tzinfo=UTC)  # 2026-12-02 10:00 ICT
    monkeypatch.setattr("apps.tasks.my_work_queries.timezone.now", lambda: fixed_now)
    today = fixed_now.date()

    p1, p1_todo, p1_done = _seed_project(
        classroom, actors, identifier="P1", group_id="grp-1", class_id="cls-1"
    )
    p2, p2_todo, _ = _seed_project(
        classroom, actors, identifier="P2", group_id="grp-2", class_id="cls-2"
    )
    p_archived, pa_todo, _ = _seed_project(
        classroom, actors, identifier="PA", group_id="grp-a", class_id="cls-a"
    )
    p_archived.archived_at = fixed_now
    p_archived.save(update_fields=["archived_at"])
    p_left, pl_todo, _ = _seed_project(
        classroom,
        actors,
        identifier="PL",
        group_id="grp-l",
        class_id="cls-l",
        member_status="ACTIVE",
    )

    sprint = Sprint.objects.create(
        project=p1,
        name="Sprint 1",
        status="ACTIVE",
        start_date=today - timedelta(days=3),
        end_date=today + timedelta(days=7),
        started_at=fixed_now - timedelta(days=3),
    )
    active_label = Label.objects.create(project=p1, name="Backend", color="#1D4ED8")
    deleted_label = Label.objects.create(
        project=p1, name="Đã xóa", color="#999999", deleted_at=fixed_now
    )

    def make_task(project, state, seq, *, assign_member=True, **kwargs):
        task = Task.objects.create(
            project=project,
            state=state,
            sequence_id=seq,
            title=kwargs.pop("title", f"Task {project.identifier}-{seq}"),
            created_by_user_id=actors["leader"],
            **kwargs,
        )
        if assign_member:
            TaskAssignment.objects.create(task=task, user_id=actors["member"])
        return task

    t_overdue = make_task(
        p1,
        p1_todo,
        1,
        title="Sửa lỗi đăng nhập",
        description_stripped="chi tiết oauth",
        priority="URGENT",
        due_date=today - timedelta(days=1),
        is_blocked=True,
        blocked_reason="Chờ API",
    )
    SprintTask.objects.create(
        sprint=sprint,
        task=t_overdue,
        added_at=fixed_now,
        scope_change_reason="Thêm việc vào chu kỳ đang chạy",
    )
    TaskLabel.objects.create(task=t_overdue, label=active_label)
    TaskLabel.objects.create(task=t_overdue, label=deleted_label)

    t_today = make_task(p1, p1_todo, 2, priority="HIGH", due_date=today)
    t_week = make_task(p2, p2_todo, 1, priority="MEDIUM", due_date=today + timedelta(days=4))
    t_upcoming = make_task(p2, p2_todo, 2, priority="LOW", due_date=today + timedelta(days=12))
    t_nodue = make_task(p1, p1_todo, 3, priority="HIGH", due_date=None)
    t_completed = make_task(
        p1,
        p1_done,
        4,
        priority="LOW",
        due_date=today - timedelta(days=2),
        completed_at=fixed_now,
    )
    # Excluded cases: unassigned to member, deleted, archived task, archived project, LEFT member
    make_task(p1, p1_todo, 5, assign_member=False, due_date=today)
    make_task(p1, p1_todo, 6, deleted_at=fixed_now, due_date=today)
    make_task(p1, p1_todo, 7, archived_at=fixed_now, due_date=today)
    make_task(p_archived, pa_todo, 1, due_date=today)
    make_task(p_left, pl_todo, 1, due_date=today)
    ProjectMember.objects.filter(project=p_left, user_id=actors["member"]).update(
        status="LEFT", left_at=fixed_now
    )

    member = client_for(actors["member"])

    with CaptureQueriesContext(connection) as queries:
        reply = member.get("/me/tasks/")
    assert reply.status_code == 200, reply.content
    assert len(queries) <= 8
    body = reply.json()
    assert body["meta"]["pagination"]["total_count"] == 5
    codes = [row["code"] for row in body["data"]]
    assert codes == ["P1-1", "P1-2", "P2-1", "P2-2", "P1-3"]  # due_date ASC NULLS LAST
    first = body["data"][0]
    assert first["project"]["classroom_class_id"] == "cls-1"
    assert first["project"]["classroom_group_id"] == "grp-1"
    assert first["state"]["group"] == "UNSTARTED"
    assert first["sprint"]["id"] == str(sprint.pk)
    assert first["labels"] == [{"id": str(active_label.pk), "name": "Backend", "color": "#1D4ED8"}]

    # Completed inclusion
    with_done = member.get("/me/tasks/", {"include_completed": "true"}).json()
    assert with_done["meta"]["pagination"]["total_count"] == 6
    assert str(t_completed.pk) in {row["id"] for row in with_done["data"]}

    # Filters: project_id, priority, is_blocked, due_bucket, search
    assert [
        r["id"] for r in member.get("/me/tasks/", {"project_id": str(p2.pk)}).json()["data"]
    ] == [
        str(t_week.pk),
        str(t_upcoming.pk),
    ]
    assert [r["id"] for r in member.get("/me/tasks/", {"is_blocked": "true"}).json()["data"]] == [
        str(t_overdue.pk)
    ]
    assert [
        r["id"] for r in member.get("/me/tasks/", {"due_bucket": "overdue"}).json()["data"]
    ] == [str(t_overdue.pk)]
    assert [r["id"] for r in member.get("/me/tasks/", {"due_bucket": "today"}).json()["data"]] == [
        str(t_today.pk)
    ]
    assert [
        r["id"] for r in member.get("/me/tasks/", {"due_bucket": "this_week"}).json()["data"]
    ] == [str(t_today.pk), str(t_week.pk)]
    assert [
        r["id"] for r in member.get("/me/tasks/", {"due_bucket": "upcoming"}).json()["data"]
    ] == [str(t_upcoming.pk)]
    assert [r["id"] for r in member.get("/me/tasks/", {"due_bucket": "no_due"}).json()["data"]] == [
        str(t_nodue.pk)
    ]
    assert [r["id"] for r in member.get("/me/tasks/", {"search": "oauth"}).json()["data"]] == [
        str(t_overdue.pk)
    ]
    assert [r["id"] for r in member.get("/me/tasks/", {"search": "P2-2"}).json()["data"]] == [
        str(t_upcoming.pk)
    ]

    # Cursor pagination across all orderings without duplicates/gaps
    for ordering in ("due_date", "-due_date", "priority", "updated_at"):
        collected = []
        cursor = None
        while True:
            params = {"ordering": ordering, "page_size": 2}
            if cursor:
                params["cursor"] = cursor
            page = member.get("/me/tasks/", params)
            assert page.status_code == 200, page.content
            payload = page.json()
            collected.extend(row["id"] for row in payload["data"])
            cursor = payload["meta"]["pagination"]["next_cursor"]
            if not payload["meta"]["pagination"]["has_next"]:
                assert cursor is None
                break
        assert len(collected) == 5 and len(set(collected)) == 5
        if ordering == "-due_date":
            assert collected[-1] == str(t_nodue.pk)
        if ordering == "priority":
            assert collected[0] == str(t_overdue.pk)

    # Filter-bound cursor validation
    first_page = member.get("/me/tasks/", {"page_size": 2}).json()
    cursor = first_page["meta"]["pagination"]["next_cursor"]
    assert member.get("/me/tasks/", {"cursor": cursor, "priority": "HIGH"}).status_code == 400
    assert member.get("/me/tasks/", {"cursor": cursor + "bad"}).status_code == 400
    assert member.get("/me/tasks/", {"unknown": "1"}).status_code == 400


def test_my_overview_aggregates_counts_projects_and_upcoming_tasks(
    classroom, actors, client_for, monkeypatch
):
    fixed_now = datetime(2026, 12, 2, 3, 0, tzinfo=UTC)
    monkeypatch.setattr("apps.tasks.my_work_queries.timezone.now", lambda: fixed_now)
    today = fixed_now.date()

    p1, p1_todo, p1_done = _seed_project(
        classroom, actors, identifier="OV", group_id="grp-ov", class_id="cls-ov"
    )
    sprint = Sprint.objects.create(
        project=p1,
        name="Sprint 2",
        status="ACTIVE",
        start_date=today - timedelta(days=1),
        end_date=today + timedelta(days=13),
        started_at=fixed_now - timedelta(days=1),
    )

    root_done = Task.objects.create(
        project=p1,
        state=p1_done,
        sequence_id=1,
        title="Hoàn thành",
        story_points=5,
        completed_at=fixed_now,
        created_by_user_id=actors["leader"],
    )
    root_open = Task.objects.create(
        project=p1,
        state=p1_todo,
        sequence_id=2,
        title="Đang mở quá hạn",
        story_points=3,
        due_date=today - timedelta(days=1),
        is_blocked=True,
        blocked_reason="Thiếu spec",
        created_by_user_id=actors["leader"],
    )
    # Subtask must not double-count root work_item_count or story_points
    sub = Task.objects.create(
        project=p1,
        state=p1_todo,
        parent=root_open,
        type="SUBTASK",
        sequence_id=3,
        title="Việc con hôm nay",
        story_points=99,
        due_date=today,
        created_by_user_id=actors["leader"],
    )
    no_due = Task.objects.create(
        project=p1,
        state=p1_todo,
        sequence_id=4,
        title="Chưa đặt hạn",
        created_by_user_id=actors["leader"],
    )
    for task in (root_done, root_open, sub, no_due):
        TaskAssignment.objects.create(task=task, user_id=actors["member"])

    member = client_for(actors["member"])
    with CaptureQueriesContext(connection) as queries:
        reply = member.get("/me/overview/")
    assert reply.status_code == 200, reply.content
    assert len(queries) <= 8
    data = reply.json()["data"]
    assert data["business_date"] == "2026-12-02"
    assert data["formula_version"] == "work-metrics-v1"
    assert data["task_counts"] == {
        "total_open": 3,
        "overdue": 1,
        "due_today": 1,
        "due_this_week": 1,
        "no_due": 1,
        "blocked": 1,
    }
    assert len(data["projects"]) == 1
    proj = data["projects"][0]
    assert proj["my_role"] == "MEMBER"
    assert proj["active_sprint"]["id"] == str(sprint.pk)
    assert proj["progress"] == {
        "work_item_count": 3,
        "completed_work_item_count": 1,
        "completion_percent": 33.33,
        "overdue_task_count": 1,
        "blocked_task_count": 1,
        "known_estimate_points": 8,
        "completed_estimate_points": 5,
    }
    assert [t["id"] for t in data["upcoming_tasks"]] == [
        str(root_open.pk),
        str(sub.pk),
        str(no_due.pk),
    ]

    # User with no projects gets clean empty response
    empty = client_for(uuid4()).get("/me/overview/")
    assert empty.status_code == 200
    assert empty.json()["data"]["projects"] == []
    assert empty.json()["data"]["task_counts"]["total_open"] == 0


def test_my_tasks_cursor_ties_nulls_ict_boundary_and_overview_cap(
    classroom, actors, client_for, monkeypatch
):
    # 2026-12-01 17:30 UTC == 2026-12-02 00:30 Asia/Ho_Chi_Minh (next calendar day in ICT)
    fixed_now = datetime(2026, 12, 1, 17, 30, tzinfo=UTC)
    monkeypatch.setattr("apps.tasks.my_work_queries.timezone.now", lambda: fixed_now)
    ict_today = datetime(2026, 12, 2, tzinfo=UTC).date()

    p1, p1_todo, _ = _seed_project(
        classroom, actors, identifier="TIE", group_id="grp-tie", class_id="cls-tie"
    )
    p1_cancelled = State.objects.create(
        project=p1,
        name="Đã hủy",
        slug="cancelled",
        color="#6B7280",
        sequence=30000,
        group="CANCELLED",
    )

    def make(seq, state=p1_todo, **kwargs):
        task = Task.objects.create(
            project=p1,
            state=state,
            sequence_id=seq,
            title=f"Tie {seq}",
            created_by_user_id=actors["leader"],
            **kwargs,
        )
        TaskAssignment.objects.create(task=task, user_id=actors["member"])
        return task

    # 3 tasks sharing identical due_date (ICT today), 3 sharing due_date=None, 1 ICT-overdue
    t_overdue_ict = make(1, priority="HIGH", due_date=ict_today - timedelta(days=1))
    tied_due = [make(i, priority="HIGH", due_date=ict_today) for i in (2, 3, 4)]
    tied_null = [make(i, priority="MEDIUM", due_date=None) for i in (5, 6, 7)]
    # Cancelled task with past due_date MUST NOT enter due_bucket=overdue
    make(8, state=p1_cancelled, priority="URGENT", due_date=ict_today - timedelta(days=3))

    # Force identical updated_at across all open tasks to exercise updated_at tie-breaker
    open_ids = [t_overdue_ict.pk, *(t.pk for t in tied_due), *(t.pk for t in tied_null)]
    Task.objects.filter(pk__in=open_ids).update(updated_at=fixed_now)

    member = client_for(actors["member"])

    # Walk page_size=1 across all 5 orderings with heavy ties & NULLs -> zero dupes, zero skips
    for ordering in ("due_date", "-due_date", "priority", "updated_at", "-updated_at"):
        seen = []
        cursor = None
        while True:
            params = {"ordering": ordering, "page_size": 1}
            if cursor:
                params["cursor"] = cursor
            res = member.get("/me/tasks/", params)
            assert res.status_code == 200, res.content
            payload = res.json()
            assert len(payload["data"]) == 1
            seen.append(payload["data"][0]["id"])
            cursor = payload["meta"]["pagination"]["next_cursor"]
            if not payload["meta"]["pagination"]["has_next"]:
                assert cursor is None
                break
        assert len(seen) == 7 and set(seen) == {str(pk) for pk in open_ids}
        if ordering in ("due_date", "-due_date"):
            assert set(seen[-3:]) == {str(t.pk) for t in tied_null}

    # Priority filter + ICT timezone boundary + CANCELLED exclusion from overdue
    assert len(member.get("/me/tasks/", {"priority": "HIGH"}).json()["data"]) == 4
    overdue_with_completed = member.get(
        "/me/tasks/", {"due_bucket": "overdue", "include_completed": "true"}
    ).json()["data"]
    assert [row["id"] for row in overdue_with_completed] == [str(t_overdue_ict.pk)]
    today_rows = member.get("/me/tasks/", {"due_bucket": "today"}).json()["data"]
    assert {row["id"] for row in today_rows} == {str(t.pk) for t in tied_due}

    # Add 18 more open tasks -> 25 total open tasks; /me/overview/ must cap upcoming_tasks at 20
    for seq in range(9, 27):
        make(seq, priority="LOW", due_date=ict_today + timedelta(days=seq))
    overview = member.get("/me/overview/").json()["data"]
    assert overview["business_date"] == "2026-12-02"
    assert overview["task_counts"]["total_open"] == 25
    assert len(overview["upcoming_tasks"]) == 20
