"""Independent public Classroom–Work scenarios using real Identity sessions."""

from uuid import uuid4

import pytest
import requests

from .http_client import wait_until
from .membership import lock, members, publish, transfer

pytestmark = pytest.mark.e2e


def test_gateway_blocks_internal_routes_and_serves_cors_and_documentation(environment):
    for route in (
        "/api/classroom/internal",
        "/api/classroom/internal/",
        "/api/classroom/internal/teachers/groups/",
    ):
        for method in ("GET", "OPTIONS"):
            assert (
                requests.request(method, environment.gateway + route, timeout=5).status_code == 404
            )
    assert (
        requests.options(environment.gateway + "/api/classroom/classes/", timeout=5).status_code
        == 204
    )
    for path in ("/api/classroom/docs/", "/api/work/docs/", "/api/classroom/openapi/"):
        assert requests.get(environment.gateway + path, timeout=10).status_code == 200


def test_identity_accounts_create_course_and_teacher_owned_class(api, accounts, section):
    actual = api("GET", section.path, token=accounts.tokens["teacher"])["data"]
    assert actual["id"] == section.classroom["id"]
    assert actual["course"] == section.course["id"]
    api("GET", section.path, token=accounts.tokens["other_teacher"], expected=404)


def test_json_enrollment_replay_limits_duplicates_and_class_authority(api, accounts, section):
    rows = [
        {"row_number": index, "email": accounts.emails[name]}
        for index, name in enumerate(("leader", "member"), 1)
    ]
    rows += [
        {"row_number": 3, "email": f"pending-{accounts.namespace}@classroom-e2e.example.edu.vn"},
        {"row_number": 4, "email": "invalid-email"},
        {"row_number": 5, "email": " " + accounts.emails["leader"].upper() + " "},
    ]
    key = str(uuid4())
    result = api(
        "POST",
        section.path + "students/",
        token=accounts.tokens["teacher"],
        body={"students": rows},
        key=key,
    )
    replay = api(
        "POST",
        section.path + "students/",
        token=accounts.tokens["teacher"],
        body={"students": rows},
        key=key,
    )
    assert result == replay
    assert [row["account_result"] for row in result["data"]["results"]] == [
        "EXISTING",
        "EXISTING",
        "CREATED",
        "FAILED",
        "NOT_REQUESTED",
    ]
    assert [row["enrollment_result"] for row in result["data"]["results"]] == [
        "ENROLLED",
        "ENROLLED",
        "ENROLLED",
        "FAILED",
        "FAILED",
    ]
    assert result["data"]["results"][-1]["reason"] == "DUPLICATE_IN_LIST"
    assert result["data"]["summary"]["duplicates"] == 1
    teachers = api("GET", section.path + "teachers/", token=accounts.tokens["leader"])["data"]
    assert [row["user_id"] for row in teachers] == [accounts.users["teacher"]]
    assert (
        api("GET", section.path + "teachers/?status=LEFT", token=accounts.tokens["leader"])["data"]
        == []
    )
    api(
        "POST",
        section.path + "students/",
        token=accounts.tokens["other_teacher"],
        body={"students": rows},
        expected=404,
    )
    for invalid in ([], rows * 26):
        api(
            "POST",
            section.path + "students/",
            token=accounts.tokens["teacher"],
            body={"students": invalid},
            expected=400,
        )
    current = api("GET", section.path, token=accounts.tokens["teacher"])["data"]
    code = api(
        "POST",
        section.path + "join-code/",
        token=accounts.tokens["teacher"],
        body={"version": current["version"]},
    )["data"]["code"]
    api(
        "POST",
        "/api/classroom/classes/join/",
        token=accounts.tokens["outsider"],
        body={"code": code},
        expected=201,
    )


def test_two_projects_link_to_group_with_idempotent_creation(api, accounts, linked_projects):
    data = linked_projects
    assert data.projects[0]["id"] != data.projects[1]["id"]
    for project, (payload, key) in zip(data.projects, data.create_requests, strict=True):
        replay = api(
            "POST",
            "/api/work/projects/",
            token=accounts.tokens["leader"],
            body=payload,
            key=key,
            expected=201,
        )["data"]
        assert replay["id"] == project["id"]
    links = api("GET", data.path + "projects/", token=accounts.tokens["teacher"])["data"]
    assert {row["project_id"] for row in links} == {project["id"] for project in data.projects}
    for project in data.projects:
        assert {row["user_id"] for row in members(api, accounts, project)} == {
            accounts.users["leader"],
            accounts.users["member"],
        }


def test_leader_fanout_preserves_work_capacity(api, environment, accounts, linked_projects):
    data = linked_projects
    api(
        "PATCH",
        f"/api/work/projects/{data.projects[0]['id']}/members/{accounts.users['leader']}/capacity/",
        token=accounts.tokens["leader"],
        body={"weekly_capacity": 30},
    )
    transfer(api, accounts, data)
    publish(environment)
    for project in data.projects:
        wait_until(
            lambda project=project: any(
                row["user_id"] == accounts.users["member"] and row["role"] == "LEADER"
                for row in members(api, accounts, project)
            ),
            "leader fanout",
        )
    leader = next(
        row
        for row in members(api, accounts, data.projects[0])
        if row["user_id"] == accounts.users["leader"]
    )
    assert float(leader["weekly_capacity"]) == 30


def test_member_removal_after_group_lock_skips_archived_project(
    api, environment, accounts, linked_projects
):
    data = linked_projects
    project = api(
        "GET", f"/api/work/projects/{data.projects[1]['id']}/", token=accounts.tokens["leader"]
    )["data"]
    api(
        "POST",
        f"/api/work/projects/{project['id']}/archive/",
        token=accounts.tokens["leader"],
        body={"expected_version": project["version"]},
    )
    lock(api, accounts, data.section)
    group = api("GET", data.path, token=accounts.tokens["leader"])["data"]
    api(
        "POST",
        data.path + "remove-member/",
        token=accounts.tokens["leader"],
        body={
            "version": group["source_version"],
            "user_id": accounts.users["member"],
            "reason": "Điều chỉnh sau chốt",
        },
    )
    publish(environment)
    wait_until(lambda: len(members(api, accounts, data.projects[0])) == 1, "active project removal")
    assert len(members(api, accounts, data.projects[1])) == 2


def test_teacher_adjustment_after_lock_updates_both_active_projects(
    api, environment, accounts, linked_projects
):
    data = linked_projects
    lock(api, accounts, data.section)
    for target, expected_users in (
        (data.second["id"], {accounts.users["leader"]}),
        (data.group["id"], {accounts.users["leader"], accounts.users["member"]}),
    ):
        api(
            "POST",
            data.section.path + "adjust-member/",
            token=accounts.tokens["teacher"],
            body={
                "user_id": accounts.users["member"],
                "target_group_id": target,
                "reason": "Giảng viên điều chỉnh nhóm",
            },
        )
        # Observe removal before moving back: the initial two members cannot satisfy this check.
        publish(environment)
        for project in data.projects:
            wait_until(
                lambda project=project, expected_users=expected_users: (
                    {row["user_id"] for row in members(api, accounts, project)} == expected_users
                ),
                "teacher adjustment reaches each active project",
            )


@pytest.mark.parametrize("mentioned,expected", [("member", 201), ("outsider", 422)])
def test_teacher_feedback_accepts_group_member_and_rejects_outsider_mention(
    api, accounts, linked_projects, mentioned, expected
):
    api(
        "POST",
        "/api/work/comments/",
        token=accounts.tokens["teacher"],
        body={
            "project_id": linked_projects.projects[0]["id"],
            "content_html": "<p>Nhóm cập nhật kế hoạch nhé.</p>",
            "mentioned_user_ids": [accounts.users[mentioned]],
        },
        expected=expected,
    )


def test_teacher_assignment_and_revocation_immediately_update_work_scope(
    api, accounts, linked_projects
):
    path = linked_projects.section.path
    assert api("GET", "/api/work/projects/", token=accounts.tokens["other_teacher"])["data"] == []
    for status, expected_count in (("ACTIVE", 2), ("LEFT", 0)):
        section = api("GET", path, token=accounts.tokens["teacher"])["data"]
        api(
            "POST",
            path + "teachers/assign/",
            token=accounts.tokens["teacher"],
            body={
                "version": section["version"],
                "user_id": accounts.users["other_teacher"],
                "role": "CO_TEACHER",
                "status": status,
            },
        )
        assert (
            len(api("GET", "/api/work/projects/", token=accounts.tokens["other_teacher"])["data"])
            == expected_count
        )
