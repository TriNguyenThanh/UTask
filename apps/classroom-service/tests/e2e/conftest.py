"""Docker lifecycle, real Identity accounts, and function-scoped business data."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from .docker_environment import ROOT, DockerEnvironment
from .http_client import GatewayClient, wait_until


def pytest_addoption(parser):
    parser.addoption("--image-prefix", default="utask")
    parser.addoption("--image-tag", default="ci")
    parser.addoption("--e2e-output", default=str(ROOT / "artifacts/classroom/backend-e2e"))
    parser.addoption("--keep-resources", action="store_true")


@pytest.fixture(scope="session")
def environment(request):
    with DockerEnvironment(
        request.config.getoption("--image-prefix"),
        request.config.getoption("--image-tag"),
        request.config.getoption("--e2e-output"),
        request.config.getoption("--keep-resources"),
    ) as stack:
        yield stack


@pytest.fixture(scope="session")
def api(environment):
    return GatewayClient(environment.gateway)


@pytest.fixture
def accounts(environment, api):
    namespace = uuid4().hex[:12].upper()
    seed = f"""
import json
from accounts.models import User
from allauth.account.models import EmailAddress
result = {{}}
for name, role in [("admin", "SYSTEM_ADMIN"), ("teacher", "TEACHER"),
                   ("other_teacher", "TEACHER"), ("leader", "STUDENT"),
                   ("member", "STUDENT"), ("outsider", "STUDENT")]:
    user = User.objects.create_user(email=name+"-{namespace}@classroom-e2e.example.edu.vn",
        password={environment.password!r}, global_role_code=role)
    EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
    result[name] = str(user.pk)
print("E2E_USERS="+json.dumps(result))
"""
    seeded = environment.command("identity", "shell", "-c", seed, capture=True)
    users = json.loads(
        next(line[10:] for line in seeded.splitlines() if line.startswith("E2E_USERS="))
    )
    emails = {name: f"{name}-{namespace}@classroom-e2e.example.edu.vn" for name in users}
    tokens = {
        name: api(
            "POST",
            "/api/auth/login",
            body={
                "email": emails[name],
                "password": environment.password,
            },
            wait_for_login_limit=True,
        )["data"]["access"]
        for name in users
    }
    return SimpleNamespace(users=users, emails=emails, tokens=tokens, namespace=namespace)


@pytest.fixture
def section(api, accounts):
    course = api(
        "POST",
        "/api/classroom/courses/",
        token=accounts.tokens["admin"],
        body={
            "code": "E" + accounts.namespace,
            "name": "Kiểm thử tích hợp",
        },
        expected=201,
    )["data"]
    classroom = api(
        "POST",
        "/api/classroom/classes/",
        token=accounts.tokens["teacher"],
        body={
            "course_id": course["id"],
            "code": "E" + accounts.namespace,
            "name": "Lớp kiểm thử",
            "term": "2026",
            "starts_on": "2026-01-01",
            "ends_on": "2026-12-31",
            "group_min_size": 1,
            "group_max_size": 4,
        },
        expected=201,
    )["data"]
    return SimpleNamespace(
        classroom=classroom,
        course=course,
        path=f"/api/classroom/classes/{classroom['id']}/",
    )


@pytest.fixture
def enrolled(api, accounts, section):
    rows = [
        {"row_number": index, "email": accounts.emails[name]}
        for index, name in enumerate(("leader", "member", "outsider"), 1)
    ]
    api(
        "POST",
        section.path + "students/",
        token=accounts.tokens["teacher"],
        body={"students": rows},
    )
    return section


@pytest.fixture
def group_data(api, accounts, enrolled):
    group = api(
        "POST",
        "/api/classroom/groups/",
        token=accounts.tokens["leader"],
        body={
            "class_id": enrolled.classroom["id"],
            "name": "Nhóm một",
        },
        expected=201,
    )["data"]
    path = f"/api/classroom/groups/{group['id']}/"
    invite = api(
        "POST",
        path + "invite-code/",
        token=accounts.tokens["leader"],
        body={
            "version": group["source_version"],
        },
    )["data"]["code"]
    api(
        "POST",
        "/api/classroom/groups/join/",
        token=accounts.tokens["member"],
        body={"code": invite},
        expected=201,
    )
    second = api(
        "POST",
        "/api/classroom/groups/",
        token=accounts.tokens["outsider"],
        body={
            "class_id": enrolled.classroom["id"],
            "name": "Nhóm hai",
        },
        expected=201,
    )["data"]
    return SimpleNamespace(section=enrolled, group=group, path=path, second=second)


@pytest.fixture
def linked_projects(api, environment, accounts, group_data):
    # Publish membership before project creation, exercising recovery from that order.
    environment.command(
        "classroom", "shell", "-c", "from apps.messaging.publisher import drain; drain()"
    )
    projects, create_requests = [], []
    for identifier in ("A" + accounts.namespace[:8], "B" + accounts.namespace[:8]):
        payload = {
            "classroom_group_id": group_data.group["id"],
            "identifier": identifier,
            "name": "Đề tài " + identifier,
        }
        key = str(uuid4())
        project = api(
            "POST",
            "/api/work/projects/",
            token=accounts.tokens["leader"],
            body=payload,
            key=key,
            expected=201,
        )["data"]
        projects.append(project)
        create_requests.append((payload, key))
    environment.command(
        "work", "shell", "-c", "from apps.messaging.publisher import drain; drain()"
    )
    wait_until(
        lambda: (
            len(api("GET", group_data.path + "projects/", token=accounts.tokens["teacher"])["data"])
            == 2
        ),
        "Classroom consumed both project.created events",
    )
    return SimpleNamespace(**vars(group_data), projects=projects, create_requests=create_requests)
