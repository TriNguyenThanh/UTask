import time
from datetime import date
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from apps.courses.models import ClassSection, ClassTeacher, Course, Enrollment
from apps.groups.models import GroupMember, StudyGroup
from common.authentication import Actor


@pytest.fixture(scope="session")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


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
    return {name: uuid4() for name in ("teacher", "leader", "member", "outsider", "admin")}


@pytest.fixture
def client_for(identity, token, actors):
    identity["roles"][str(actors["teacher"])] = ["TEACHER"]
    identity["roles"][str(actors["admin"])] = ["SYSTEM_ADMIN"]

    def make(user_id):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer " + token(user_id))
        return client

    return make


@pytest.fixture
def command_request(token):
    def make(actor_id, path, key=None, roles=("STUDENT",)):
        request = APIRequestFactory().post(
            path,
            {},
            format="json",
            HTTP_AUTHORIZATION="Bearer " + token(actor_id),
            HTTP_IDEMPOTENCY_KEY=str(key or uuid4()),
        )
        force_authenticate(request, user=Actor(actor_id))
        request.user = Actor(actor_id)
        request.classroom_roles = set(roles)
        return request

    return make


@pytest.fixture
def section(db, actors):
    course = Course.objects.create(code="SE", name="Công nghệ phần mềm")
    section = ClassSection.objects.create(
        course=course,
        code="SE01",
        name="Lớp SE",
        term="2026",
        starts_on=date(2026, 1, 1),
        ends_on=date(2026, 12, 31),
        group_max_size=3,
    )
    ClassTeacher.objects.create(class_section=section, user_id=actors["teacher"], role="PRIMARY")
    for name in ("leader", "member", "outsider"):
        Enrollment.objects.create(class_section=section, user_id=actors[name])
    return section


@pytest.fixture
def group(section, actors):
    group = StudyGroup.objects.create(class_section=section, name="Nhóm A")
    for name, role in (("leader", "LEADER"), ("member", "MEMBER")):
        GroupMember.objects.create(
            class_section=section,
            group=group,
            role=role,
            enrollment=Enrollment.objects.get(class_section=section, user_id=actors[name]),
        )
    return group


@pytest.fixture
def post_command():
    def post(client, path, payload, key=None):
        return client.post(path, payload, format="json", HTTP_IDEMPOTENCY_KEY=str(key or uuid4()))

    return post


pytest_plugins = ["tests.fixtures.identity"]
