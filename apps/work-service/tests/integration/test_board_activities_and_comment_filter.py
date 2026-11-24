from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.collaboration.models import Attachment, Comment
from apps.integrations.models import TaskGitHubLink
from apps.projects.models import State, UserProjection
from apps.tasks.models import Epic, Label, Task, TaskAssignment, TaskLabel

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_board_enriched_cards_new_filters_and_query_budget(task_api, actors, client_for):
    leader, _, create = task_api
    member = client_for(actors["member"])
    now = timezone.now()

    UserProjection.objects.create(
        user_id=actors["member"],
        display_name="Nguyễn Văn Minh",
        avatar_url="https://cdn.example/minh.png",
        source_event_id="evt-1",
        source_occurred_at=now,
    )
    t1 = create(
        title="Xây dựng API bảng công việc",
        description_html="<p>Chi tiết dài cho thẻ</p>",
        story_points=5,
        priority="HIGH",
        type="STORY",
    )
    project_id = t1["project_id"]
    epic = Epic.objects.create(project_id=project_id, name="Epic Nền tảng")
    label = Label.objects.create(project_id=project_id, name="API", color="#0EA5E9")
    deleted_label = Label.objects.create(
        project_id=project_id, name="Cũ", color="#94A3B8", deleted_at=now
    )
    Task.objects.filter(pk=t1["id"]).update(
        epic=epic, is_blocked=True, blocked_reason="Chờ duyệt thiết kế"
    )
    TaskLabel.objects.create(task_id=t1["id"], label=label)
    TaskLabel.objects.create(task_id=t1["id"], label=deleted_label)

    # Subtask hidden by default, counted in subtasks_count
    state = State.objects.get(pk=t1["state_id"])
    sub = Task.objects.create(
        project_id=project_id,
        state=state,
        parent_id=t1["id"],
        type="SUBTASK",
        sequence_id=99,
        title="Việc con chi tiết",
        created_by_user_id=actors["leader"],
    )
    TaskAssignment.objects.create(task=sub, user_id=actors["member"])

    Comment.objects.create(
        task_id=t1["id"],
        user_id=actors["member"],
        content_html="<p>Góp ý</p>",
        content_stripped="Góp ý",
    )
    Attachment.objects.create(
        task_id=t1["id"],
        uploaded_by_user_id=actors["member"],
        file_name="spec.pdf",
        file_size=128,
        content_type="application/pdf",
        storage_key=f"work/{t1['id']}/spec.pdf",
        status="CONFIRMED",
        expires_at=now + timedelta(minutes=15),
        confirmed_at=now,
    )
    TaskGitHubLink.objects.create(
        task_id=t1["id"],
        github_repo_id="repo-1",
        connection_generation=1,
        source_version=1,
        link_type="PULL_REQUEST",
        github_ref_id="1",
        github_url="https://github.com/org/repo/pull/1",
        confirmation_status="CONFIRMED",
        confirmed_by_user_id=actors["leader"],
        confirmed_at=now,
        is_verified=True,
        synced_at=now,
    )

    # Second task with PENDING PR (has_pull_request MUST be False)
    t2 = create(title="Khác mục tiêu", priority="LOW", type="BUG")
    TaskGitHubLink.objects.create(
        task_id=t2["id"],
        github_repo_id="repo-1",
        connection_generation=1,
        source_version=1,
        link_type="PULL_REQUEST",
        github_ref_id="2",
        github_url="https://github.com/org/repo/pull/2",
        confirmation_status="PENDING",
        synced_at=now,
    )

    route = f"/projects/{project_id}/kanban/"
    with CaptureQueriesContext(connection) as queries:
        reply = member.get(route)
    assert reply.status_code == 200, reply.content
    assert len(queries) <= 10
    data = reply.json()["data"]
    assert data["total_tasks"] == 2  # Subtask hidden by default
    cards = {c["id"]: c for col in data["columns"] for c in col["tasks"]}
    assert sub.pk not in cards
    c1 = cards[t1["id"]]
    assert c1["type"] == "STORY"
    assert c1["priority"] == "HIGH"
    assert c1["story_points"] == 5
    assert c1["epic_id"] == str(epic.pk)
    assert c1["parent_id"] is None
    assert c1["assignees"] == [
        {
            "user_id": str(actors["member"]),
            "display_name": "Nguyễn Văn Minh",
            "avatar_url": "https://cdn.example/minh.png",
        }
    ]
    assert c1["labels"] == [{"id": str(label.pk), "name": "API", "color": "#0EA5E9"}]
    assert c1["is_blocked"] is True
    assert c1["blocked_reason"] == "Chờ duyệt thiết kế"
    assert c1["subtasks_count"] == 1
    assert c1["comments_count"] == 1
    assert c1["attachments_count"] == 1
    assert c1["has_pull_request"] is True
    assert cards[t2["id"]]["has_pull_request"] is False
    assert member.get(route, {"is_blocked": "true"}).json()["data"]["total_tasks"] == 1
    assert member.get(route, {"is_blocked": "false"}).json()["data"]["total_tasks"] == 1

    # include_subtasks=true reveals subtask
    with_sub = member.get(route, {"include_subtasks": "true"}).json()["data"]
    assert with_sub["total_tasks"] == 3

    # New filters: epic_id, label_id, type, search
    assert member.get(route, {"epic_id": str(epic.pk)}).json()["data"]["total_tasks"] == 1
    assert member.get(route, {"label_id": str(label.pk)}).json()["data"]["total_tasks"] == 1
    assert member.get(route, {"type": "BUG"}).json()["data"]["total_tasks"] == 1
    assert member.get(route, {"type": "SUBTASK"}).json()["data"]["total_tasks"] == 1
    assert member.get(route, {"search": "bảng công việc"}).json()["data"]["total_tasks"] == 1


def test_project_activities_filters_enrichment_pagination_and_permissions(
    task_api, actors, client_for
):
    leader, _, create = task_api
    now = timezone.now()
    UserProjection.objects.create(
        user_id=actors["leader"],
        display_name="Trần Trưởng Nhóm",
        avatar_url="https://cdn.example/leader.png",
        source_event_id="evt-leader",
        source_occurred_at=now,
    )
    task = create(title="Công việc nhật ký")
    project_id = task["project_id"]
    label_resp = leader.post(
        f"/projects/{project_id}/labels/",
        {"name": "Docs", "color": "#10B981"},
        format="json",
    )
    assert label_resp.status_code == 201
    comment_resp = client_for(actors["member"]).post(
        "/comments/",
        {"project_id": project_id, "content_html": "<p>Nhận xét dự án</p>"},
        format="json",
    )
    assert comment_resp.status_code == 201

    route = f"/projects/{project_id}/activities/"
    assert client_for(actors["outsider"]).get(route).status_code == 404
    assert client_for(actors["teacher"]).get(route).status_code == 200

    all_reply = leader.get(route, {"page_size": 2})
    assert all_reply.status_code == 200, all_reply.content
    page1 = all_reply.json()
    assert page1["meta"]["pagination"]["total_count"] >= 4
    assert page1["meta"]["pagination"]["has_next"] is True
    cursor = page1["meta"]["pagination"]["next_cursor"]

    page2 = leader.get(route, {"page_size": 2, "cursor": cursor})
    assert page2.status_code == 200
    assert {r["id"] for r in page1["data"]}.isdisjoint(r["id"] for r in page2.json()["data"])

    # Cursor bound to filters
    assert leader.get(route, {"cursor": cursor, "subject_type": "TASK"}).status_code == 400

    # Filters & enrichment
    task_only = leader.get(route, {"subject_type": "TASK", "verb": "created"}).json()["data"]
    assert len(task_only) == 1
    assert task_only[0]["subject_type"] == "TASK"
    assert task_only[0]["subject_id"] == task["id"]
    assert task_only[0]["actor_display_name"] == "Trần Trưởng Nhóm"
    assert task_only[0]["actor_avatar_url"] == "https://cdn.example/leader.png"

    by_actor = leader.get(route, {"actor_user_id": str(actors["member"])}).json()["data"]
    assert len(by_actor) == 1 and by_actor[0]["subject_type"] == "COMMENT"

    future = (now + timedelta(days=1)).isoformat()
    past = (now - timedelta(days=1)).isoformat()
    assert leader.get(route, {"created_from": past, "created_to": future}).status_code == 200
    assert leader.get(route, {"created_from": future, "created_to": past}).status_code == 400


def test_comment_list_filters_by_is_teacher_feedback(task_api, actors, client_for):
    leader, _, create = task_api
    task = create(title="Công việc phản hồi")
    project_id = task["project_id"]
    member = client_for(actors["member"])
    teacher = client_for(actors["teacher"])

    assert (
        member.post(
            "/comments/", {"task_id": task["id"], "content_html": "Bình luận SV"}, format="json"
        ).status_code
        == 201
    )
    assert (
        teacher.post(
            "/comments/", {"task_id": task["id"], "content_html": "Nhận xét GV"}, format="json"
        ).status_code
        == 201
    )
    assert (
        member.post(
            "/comments/",
            {"project_id": project_id, "content_html": "Bình luận dự án SV"},
            format="json",
        ).status_code
        == 201
    )
    assert (
        teacher.post(
            "/comments/",
            {"project_id": project_id, "content_html": "Nhận xét dự án GV"},
            format="json",
        ).status_code
        == 201
    )

    for route in (f"/tasks/{task['id']}/comments/", f"/projects/{project_id}/comments/"):
        assert leader.get(route).json()["meta"]["pagination"]["total_count"] == 2
        only_fb = leader.get(route, {"is_teacher_feedback": "true"}).json()
        assert only_fb["meta"]["pagination"]["total_count"] == 1
        assert only_fb["data"][0]["is_teacher_feedback"] is True
        only_normal = leader.get(route, {"is_teacher_feedback": "false"}).json()
        assert only_normal["meta"]["pagination"]["total_count"] == 1
        assert only_normal["data"][0]["is_teacher_feedback"] is False
        invalid = leader.get(route, {"is_teacher_feedback": "maybe"})
        assert invalid.status_code == 400
        assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"

        # Cursor bound to is_teacher_feedback
        paged = leader.get(route, {"page_size": 1}).json()
        cursor = paged["meta"]["pagination"]["next_cursor"]
        assert (
            leader.get(route, {"cursor": cursor, "is_teacher_feedback": "true"}).status_code == 400
        )


def test_board_column_pagination_new_filters_missing_projection_and_deleted_exclusions(
    task_api, actors, client_for
):
    leader, _, create = task_api
    now = timezone.now()
    # Member has UserProjection; leader intentionally does NOT -> fallback display_name=""
    UserProjection.objects.create(
        user_id=actors["member"],
        display_name="Phạm Thành Viên",
        avatar_url=None,
        source_event_id="evt-m",
        source_occurred_at=now,
    )
    t1 = create(
        title="Thẻ một",
        description_html="<p>Từ khóa bí mật alpha</p>",
        assignee_ids=[str(actors["member"]), str(actors["leader"])],
        type="STORY",
    )
    project_id = t1["project_id"]
    state_id = t1["state_id"]
    epic = Epic.objects.create(project_id=project_id, name="Epic Board")
    lbl_b = Label.objects.create(project_id=project_id, name="Zeta", color="#111111")
    lbl_a = Label.objects.create(project_id=project_id, name="Alpha", color="#222222")
    Task.objects.filter(pk=t1["id"]).update(epic=epic)
    TaskLabel.objects.create(task_id=t1["id"], label=lbl_b)
    TaskLabel.objects.create(task_id=t1["id"], label=lbl_a)

    t2 = create(title="Thẻ hai", type="STORY")
    Task.objects.filter(pk=t2["id"]).update(epic=epic)
    TaskLabel.objects.create(task_id=t2["id"], label=lbl_a)

    # Soft-deleted / PENDING related items MUST NOT increment counts or flip has_pull_request
    Task.objects.create(
        project_id=project_id,
        state_id=state_id,
        parent_id=t1["id"],
        type="SUBTASK",
        sequence_id=50,
        title="Subtask đã xóa",
        created_by_user_id=actors["leader"],
        deleted_at=now,
    )
    Comment.objects.create(
        task_id=t1["id"],
        user_id=actors["member"],
        content_html="<p>đã xóa</p>",
        content_stripped="đã xóa",
        deleted_at=now,
    )
    Attachment.objects.create(
        task_id=t1["id"],
        uploaded_by_user_id=actors["member"],
        file_name="pending.pdf",
        file_size=100,
        content_type="application/pdf",
        storage_key=f"work/{t1['id']}/pending.pdf",
        status="PENDING",
        expires_at=now + timedelta(minutes=15),
    )
    Attachment.objects.create(
        task_id=t1["id"],
        uploaded_by_user_id=actors["member"],
        file_name="deleted.pdf",
        file_size=100,
        content_type="application/pdf",
        storage_key=f"work/{t1['id']}/deleted.pdf",
        status="CONFIRMED",
        expires_at=now + timedelta(minutes=15),
        confirmed_at=now,
        deleted_at=now,
    )
    TaskGitHubLink.objects.create(
        task_id=t1["id"],
        github_repo_id="repo-x",
        connection_generation=1,
        source_version=1,
        link_type="PULL_REQUEST",
        github_ref_id="99",
        github_url="https://github.com/org/repo/pull/99",
        confirmation_status="CONFIRMED",
        confirmed_by_user_id=actors["leader"],
        confirmed_at=now,
        is_verified=True,
        synced_at=now,
        deleted_at=now,
    )

    col_route = f"/projects/{project_id}/kanban/states/{state_id}/tasks/"
    page1 = leader.get(col_route, {"epic_id": str(epic.pk), "page_size": 1})
    assert page1.status_code == 200, page1.content
    d1 = page1.json()["data"]
    assert d1["column_total_tasks"] == 2 and d1["has_more"] is True
    card1 = d1["tasks"][0]
    assert card1["subtasks_count"] == 0
    assert card1["comments_count"] == 0
    assert card1["attachments_count"] == 0
    assert card1["has_pull_request"] is False
    # Labels deterministically ordered by name: Alpha then Zeta
    assert [row["name"] for row in card1["labels"]] == ["Alpha", "Zeta"]
    # Both assignees present; missing UserProjection falls back to display_name=""
    assignees_by_id = {row["user_id"]: row for row in card1["assignees"]}
    assert assignees_by_id[str(actors["member"])]["display_name"] == "Phạm Thành Viên"
    assert assignees_by_id[str(actors["leader"])] == {
        "user_id": str(actors["leader"]),
        "display_name": "",
        "avatar_url": None,
    }

    # Cursor valid with matching filter, rejected when ANY new filter changes
    cursor = d1["next_cursor"]
    page2 = leader.get(col_route, {"epic_id": str(epic.pk), "page_size": 1, "cursor": cursor})
    assert page2.status_code == 200
    assert page2.json()["data"]["tasks"][0]["id"] == t2["id"]
    for changed in (
        {"epic_id": str(epic.pk), "label_id": str(lbl_a.pk), "cursor": cursor},
        {"epic_id": str(epic.pk), "type": "STORY", "cursor": cursor},
        {"epic_id": str(epic.pk), "search": "Thẻ", "cursor": cursor},
        {"epic_id": str(epic.pk), "include_subtasks": "true", "cursor": cursor},
    ):
        assert leader.get(col_route, changed).status_code == 400

    # Search by task code and by description_stripped
    board_route = f"/projects/{project_id}/kanban/"
    assert leader.get(board_route, {"search": t1["code"]}).json()["data"]["total_tasks"] == 1
    assert leader.get(board_route, {"search": "bí mật alpha"}).json()["data"]["total_tasks"] == 1

    # Invalid filter inputs rejected with 400
    for bad in (
        {"epic_id": "not-uuid"},
        {"label_id": "not-uuid"},
        {"type": "INVALID"},
        {"search": ""},
        {"include_subtasks": "not-bool"},
    ):
        assert leader.get(board_route, bad).status_code == 400


def test_project_activities_all_8_subjects_isolation_null_actor_and_query_budget(
    task_api, actors, client_for
):
    from django.db import transaction

    from apps.messaging.services.audit import record_activity
    from apps.projects.models import Project, ProjectMember

    leader, _, create = task_api
    task = create(title="Task hoạt động")
    project_id = task["project_id"]
    project = Project.objects.get(pk=project_id)

    # Trigger activities across all remaining subject types:
    # PROJECT, PROJECT_MEMBER, STATE, EPIC, LABEL, COMMENT (task + project), SPRINT
    assert (
        leader.patch(
            f"/projects/{project_id}/members/{actors['member']}/capacity/",
            {"weekly_capacity": 20},
            format="json",
        ).status_code
        == 200
    )
    assert (
        leader.post(
            f"/projects/{project_id}/states/",
            {"name": "QA", "color": "#8B5CF6", "sequence": 45000, "group": "REVIEW"},
            format="json",
        ).status_code
        == 201
    )
    assert (
        leader.post(
            f"/projects/{project_id}/epics/", {"name": "Epic QA"}, format="json"
        ).status_code
        == 201
    )
    assert (
        leader.post(
            f"/projects/{project_id}/labels/",
            {"name": "QA", "color": "#F59E0B"},
            format="json",
        ).status_code
        == 201
    )
    assert (
        leader.post(
            "/comments/", {"task_id": task["id"], "content_html": "Bình luận task"}, format="json"
        ).status_code
        == 201
    )
    assert (
        leader.post(
            f"/projects/{project_id}/sprints/", {"name": "Sprint QA"}, format="json"
        ).status_code
        == 201
    )
    # System activity with actor_user_id=None
    with transaction.atomic():
        record_activity(project, None, "synced")

    # Separate Project B MUST NOT leak into Project A's activity feed
    other = Project.objects.create(
        identifier="ISO", name="Dự án khác", classroom_group_id="iso-group"
    )
    ProjectMember.objects.create(
        project=other, user_id=actors["leader"], role="LEADER", joined_at=timezone.now()
    )
    with transaction.atomic():
        record_activity(other, actors["leader"], "other_project_event")

    route = f"/projects/{project_id}/activities/"
    with CaptureQueriesContext(connection) as queries:
        res = leader.get(route, {"page_size": 50})
    assert res.status_code == 200, res.content
    assert len(queries) <= 10
    rows = res.json()["data"]
    assert all(row["verb"] != "other_project_event" for row in rows)
    assert any(
        row["verb"] == "synced"
        and row["actor_user_id"] is None
        and row["actor_display_name"] == ""
        and row["actor_avatar_url"] is None
        for row in rows
    )

    # Every one of the 8 subject types is individually filterable and has non-null subject_id
    for subject_type in (
        "PROJECT",
        "PROJECT_MEMBER",
        "STATE",
        "TASK",
        "EPIC",
        "LABEL",
        "COMMENT",
        "SPRINT",
    ):
        filtered = leader.get(route, {"subject_type": subject_type}).json()["data"]
        assert len(filtered) >= 1, subject_type
        assert all(
            r["subject_type"] == subject_type and r["subject_id"] is not None for r in filtered
        )

    # Invalid filter inputs -> 400
    for bad in (
        {"subject_type": "UNKNOWN"},
        {"actor_user_id": "not-uuid"},
        {"created_from": "not-a-date"},
        {"extra_param": "1"},
    ):
        assert leader.get(route, bad).status_code == 400
