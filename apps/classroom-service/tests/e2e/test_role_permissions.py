"""Finalized role boundaries through real Identity, Classroom, Work and Kafka."""

from uuid import uuid4

import pytest

from tests.e2e.http_client import wait_until

pytestmark = pytest.mark.e2e


def test_course_owner_and_revoked_teacher_cannot_replay(api, accounts, environment):
    key = str(uuid4())
    payload = {"code": "R" + accounts.namespace, "name": "Môn của giảng viên"}
    created = api(
        "POST",
        "/api/classroom/courses/",
        token=accounts.tokens["teacher"],
        body=payload,
        key=key,
        expected=201,
    )
    course = created["data"]
    assert course["created_by_id"] == accounts.users["teacher"]
    path = f"/api/classroom/courses/{course['id']}/"
    for method, suffix, body in (
        ("PATCH", "", {"code": course["code"], "name": "Không được sửa"}),
        ("POST", "archive/", {}),
    ):
        api(method, path + suffix, token=accounts.tokens["other_teacher"], body=body, expected=403)
        api(method, path + suffix, token=accounts.tokens["leader"], body=body, expected=403)
    changed = api(
        "PATCH",
        path,
        token=accounts.tokens["teacher"],
        body={"code": course["code"], "name": "Đã sửa"},
    )
    assert changed["data"]["created_by_id"] == accounts.users["teacher"]
    api(
        "DELETE",
        f"/api/auth/admin/users/{accounts.users['teacher']}/roles",
        token=accounts.tokens["admin"],
        body={"role_code": "TEACHER"},
    )
    api("GET", "/api/auth/users/me", token=accounts.tokens["teacher"], expected=401)
    accounts.tokens["teacher"] = api(
        "POST",
        "/api/auth/login",
        body={"email": accounts.emails["teacher"], "password": environment.password},
        wait_for_login_limit=True,
    )["data"]["access"]
    api(
        "POST",
        "/api/classroom/courses/",
        token=accounts.tokens["teacher"],
        body=payload,
        key=key,
        expected=403,
    )
    api(
        "PATCH",
        path,
        token=accounts.tokens["teacher"],
        body={"code": course["code"], "name": "Bị thu hồi"},
        expected=403,
    )
    archived = api("POST", path + "archive/", token=accounts.tokens["admin"], body={})
    assert archived["data"]["archived_at"]


def test_admin_group_operations_do_not_grant_unselected_group_rights(api, accounts, group_data):
    path = group_data.path
    admin = accounts.tokens["admin"]
    teacher = accounts.tokens["teacher"]
    leader = accounts.tokens["leader"]
    api("GET", path, token=accounts.tokens["outsider"], expected=404)
    current = api("GET", path, token=admin)["data"]
    all_groups = api("GET", "/api/classroom/groups/", token=admin)["data"]
    assert current["id"] in {row["id"] for row in all_groups}
    changed = api(
        "PATCH",
        path,
        token=admin,
        body={"version": current["source_version"], "name": "Admin cập nhật"},
    )["data"]
    api("GET", path + "activities/", token=admin)
    for suffix in ("members/", "projects/"):
        api("GET", path + suffix, token=admin, expected=404)
    api(
        "POST",
        path + "invite-code/",
        token=admin,
        body={"version": changed["source_version"]},
        expected=404,
    )
    api(
        "POST",
        path + "transfer-leader/",
        token=admin,
        body={
            "version": changed["source_version"],
            "user_id": accounts.users["member"],
            "reason": "Không cấp quyền chuyển",
        },
        expected=404,
    )
    api(
        "POST",
        path + "remove-member/",
        token=teacher,
        body={
            "version": changed["source_version"],
            "user_id": accounts.users["member"],
            "reason": "Giảng viên loại thành viên",
        },
    )
    created = api(
        "POST",
        "/api/classroom/groups/",
        token=admin,
        expected=201,
        body={
            "class_id": group_data.section.classroom["id"],
            "name": "Tạo thay sinh viên",
            "leader_id": accounts.users["member"],
        },
    )["data"]
    members = api(
        "GET",
        f"/api/classroom/groups/{created['id']}/members/",
        token=teacher,
    )["data"]
    assert [(row["user_id"], row["role"]) for row in members] == [
        (accounts.users["member"], "LEADER")
    ]
    section = api("GET", group_data.section.path, token=admin)["data"]
    api(
        "POST",
        group_data.section.path + "lock-grouping/",
        token=admin,
        body={"version": section["version"]},
    )
    api(
        "POST",
        group_data.section.path + "adjust-member/",
        token=admin,
        body={
            "user_id": accounts.users["member"],
            "target_group_id": group_data.group["id"],
            "reason": "Giữ quy tắc trưởng nhóm",
        },
        expected=409,
    )
    api("GET", path + "members/", token=leader)


def test_primary_and_co_teacher_both_lose_authority_when_global_role_revoked(
    api,
    accounts,
    linked_projects,
    environment,
):
    section = linked_projects.section
    project = linked_projects.projects[0]
    current = api("GET", section.path, token=accounts.tokens["teacher"])["data"]
    api(
        "POST",
        section.path + "teachers/assign/",
        token=accounts.tokens["teacher"],
        body={
            "version": current["version"],
            "user_id": accounts.users["other_teacher"],
            "role": "CO_TEACHER",
            "status": "ACTIVE",
        },
    )
    for name in ("teacher", "other_teacher"):
        token = accounts.tokens[name]
        api("GET", section.path, token=token)
        api("GET", linked_projects.path + "members/", token=token)
        api("GET", f"/api/work/projects/{project['id']}/", token=token)
        api(
            "DELETE",
            f"/api/auth/admin/users/{accounts.users[name]}/roles",
            token=accounts.tokens["admin"],
            body={"role_code": "TEACHER"},
        )
        api("GET", "/api/auth/users/me", token=token, expected=401)
        token = api(
            "POST",
            "/api/auth/login",
            body={"email": accounts.emails[name], "password": environment.password},
            wait_for_login_limit=True,
        )["data"]["access"]
        api("GET", section.path, token=token, expected=404)
        api("GET", linked_projects.path + "members/", token=token, expected=404)
        api("GET", f"/api/work/projects/{project['id']}/", token=token, expected=404)
        api(
            "POST",
            "/api/work/comments/",
            token=token,
            body={"project_id": project["id"], "content_html": "<p>Đã mất quyền</p>"},
            expected=404,
        )
    teachers = api("GET", section.path + "teachers/", token=accounts.tokens["admin"])["data"]
    assert {row["user_id"] for row in teachers if row["status"] == "ACTIVE"} == {
        accounts.users["teacher"],
        accounts.users["other_teacher"],
    }


def test_admin_adjustment_and_exit_preserve_scoped_membership(api, accounts, enrolled):
    admin = accounts.tokens["admin"]
    group = api(
        "POST",
        "/api/classroom/groups/",
        token=accounts.tokens["teacher"],
        expected=201,
        body={
            "class_id": enrolled.classroom["id"],
            "name": "Giảng viên tạo thay",
            "leader_id": accounts.users["leader"],
        },
    )["data"]
    current = api("GET", enrolled.path, token=admin)["data"]
    api("POST", enrolled.path + "lock-grouping/", token=admin, body={"version": current["version"]})
    adjusted = api(
        "POST",
        enrolled.path + "adjust-member/",
        token=admin,
        body={
            "user_id": accounts.users["member"],
            "target_group_id": group["id"],
            "reason": "Admin phân nhóm sau khi chốt",
        },
    )["data"]
    assert adjusted["group_id"] == group["id"]
    path = f"/api/classroom/groups/{group['id']}/"
    current = api("GET", path, token=admin)["data"]
    api(
        "POST",
        path + "remove-member/",
        token=admin,
        body={
            "version": current["source_version"],
            "user_id": accounts.users["member"],
            "reason": "Admin loại thành viên",
        },
    )
    enrollments = api("GET", enrolled.path + "enrollments/", token=admin)["data"]
    target = next(row for row in enrollments if row["user_id"] == accounts.users["outsider"])
    removed = api(
        "POST",
        enrolled.path + f"enrollments/{target['id']}/exit/",
        token=admin,
        body={"reason": "Admin kết thúc ghi danh"},
    )["data"]
    assert removed["status"] == "REMOVED"
    remaining = api("GET", path + "members/?status=ACTIVE", token=accounts.tokens["teacher"])[
        "data"
    ]
    assert [(row["user_id"], row["role"]) for row in remaining] == [
        (accounts.users["leader"], "LEADER")
    ]


def test_admin_feedback_is_own_comment_only_without_project_read(api, accounts, linked_projects):
    project = linked_projects.projects[0]
    admin = accounts.tokens["admin"]
    for suffix in ("", "comments/"):
        api("GET", f"/api/work/projects/{project['id']}/" + suffix, token=admin, expected=404)
    payload = {"project_id": project["id"], "content_html": "<p>Nhận xét của quản trị</p>"}
    created = api("POST", "/api/work/comments/", token=admin, body=payload, expected=201)["data"]
    assert created["is_teacher_feedback"] is False
    path = f"/api/work/comments/{created['id']}/"
    api("PATCH", path, token=admin, body={"content_html": "<p>Nhận xét đã sửa</p>"})
    member_comment = api(
        "POST",
        "/api/work/comments/",
        token=accounts.tokens["leader"],
        body=payload,
        expected=201,
    )["data"]
    api(
        "DELETE",
        f"/api/work/comments/{member_comment['id']}/",
        token=admin,
        expected=404,
    )
    api("DELETE", path, token=admin)


def test_admin_member_removal_reaches_all_work_projects(api, accounts, linked_projects):
    current = api("GET", linked_projects.path, token=accounts.tokens["admin"])["data"]
    api(
        "POST",
        linked_projects.path + "remove-member/",
        token=accounts.tokens["admin"],
        body={
            "version": current["source_version"],
            "user_id": accounts.users["member"],
            "reason": "Kiểm tra đồng bộ quyền Admin qua Kafka",
        },
    )
    for project in linked_projects.projects:
        wait_until(
            lambda project=project: (
                {
                    row["user_id"]
                    for row in api(
                        "GET",
                        f"/api/work/projects/{project['id']}/members/",
                        token=accounts.tokens["teacher"],
                    )["data"]
                }
                == {accounts.users["leader"]}
            ),
            "Admin removal propagated to each active Work project",
        )
