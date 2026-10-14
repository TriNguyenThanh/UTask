import json
import time
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from rest_framework.test import APIClient

from tests.fixtures.classroom import FixtureClassroom, GroupMemberFact, GroupSnapshot


@pytest.fixture(autouse=True)
def classroom():
    FixtureClassroom.groups = {}
    FixtureClassroom.teachers = {}
    yield FixtureClassroom


@pytest.fixture(scope="session")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def identity(monkeypatch, signing_key):
    class Reply:
        status_code = 200

        def __init__(self, body):
            self.body = body

        def raise_for_status(self):
            pass

        def json(self):
            return self.body

    state = {
        "active": True,
        "keys": [json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))],
        "calls": [],
    }

    def get(url, **kwargs):
        assert url.endswith("/.well-known/jwks.json")
        assert kwargs["timeout"] == settings.BACKEND_HTTP_TIMEOUT
        return Reply({"keys": state["keys"]})

    def post(url, **kwargs):
        assert url.endswith("/api/v1/internal/auth/session-status")
        assert kwargs["headers"]["X-Service-Key"] == "test-work-key"
        state["calls"].append(kwargs)
        return Reply(
            {
                "success": True,
                "message": "ok",
                "data": {"active": state["active"]},
                "meta": None,
                "error": None,
            }
        )

    monkeypatch.setattr("infrastructure.identity.requests.get", get)
    monkeypatch.setattr("infrastructure.identity.requests.post", post)
    return state


@pytest.fixture
def token(signing_key):
    def make(user_id, **overrides):
        claims = {
            "sub": str(user_id),
            "iss": settings.IDENTITY_JWT_ISSUER,
            "aud": settings.IDENTITY_JWT_AUDIENCE,
            "exp": int(time.time()) + 600,
            "token_type": "access",
        }
        claims.update(overrides)
        return jwt.encode(claims, signing_key, algorithm="RS256")

    return make


@pytest.fixture
def actors():
    return {name: uuid4() for name in ("leader", "member", "outsider", "teacher")}


@pytest.fixture
def client_for(identity, token):
    def make(user_id):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer " + token(user_id))
        return client

    return make


@pytest.fixture
def group(classroom, actors):
    snapshot = GroupSnapshot(
        "group-1",
        "class-1",
        1,
        (GroupMemberFact(actors["leader"], "LEADER"), GroupMemberFact(actors["member"], "MEMBER")),
    )
    classroom.groups[snapshot.group_id] = snapshot
    classroom.teachers[actors["teacher"]] = [snapshot.group_id]
    return snapshot


@pytest.fixture
def project_payload(group):
    return {
        "identifier": "UT",
        "name": "Đề tài UTask",
        "classroom_group_id": group.group_id,
        "tech_stack": {"backend": "Django"},
    }


@pytest.fixture
def created_project(db, client_for, actors, project_payload):
    response = client_for(actors["leader"]).post(
        "/api/v1/projects/", project_payload, format="json", HTTP_IDEMPOTENCY_KEY="project-create"
    )
    assert response.status_code == 201, response.content
    return response.json()["data"]


@pytest.fixture
def task_api(created_project, client_for, actors):
    leader = client_for(actors["leader"])
    route = f"/api/v1/projects/{created_project['id']}/tasks/"

    def create(**changes):
        key = changes.pop("key", str(uuid4()))
        body = {"title": "Xây dựng API", "assignee_ids": [str(actors["member"])], **changes}
        response = leader.post(route, body, format="json", HTTP_IDEMPOTENCY_KEY=key)
        assert response.status_code == 201, response.content
        return response.json()["data"]

    return leader, route, create


pytest_plugins = [
    "tests.fixtures.project_api",
    "tests.fixtures.storage",
    "tests.fixtures.tasks",
    "tests.fixtures.collaboration",
]


@pytest.fixture(autouse=True)
def feedback_verifier(classroom, monkeypatch):
    from datetime import timedelta

    from django.utils import timezone

    from infrastructure.collaboration_scope import VerifiedFeedbackScope

    def verify(project, actor):
        assert project.classroom_group_id in classroom().teacher_group_ids(actor)
        return VerifiedFeedbackScope(
            actor.id,
            project.pk,
            project.classroom_group_id,
            1,
            timezone.now() + timedelta(minutes=1),
        )

    monkeypatch.setattr(classroom, "teacher_feedback_scope", staticmethod(verify), raising=False)
