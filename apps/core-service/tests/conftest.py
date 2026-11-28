"""Shared test fixtures for UTask Core Service (Identity, Classroom, Work)."""

import hashlib
from uuid import uuid4

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient


@pytest.fixture(autouse=True)
def clear_core_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def seed_global_roles(db):
    from apps.accounts.models import GlobalRole, GlobalRoleCode

    roles = {}
    for code, name, description in (
        (GlobalRoleCode.SYSTEM_ADMIN, "Quản trị hệ thống", "Quản trị viên toàn hệ thống."),
        (GlobalRoleCode.TEACHER, "Giảng viên", "Giảng viên phụ trách lớp học."),
        (GlobalRoleCode.STUDENT, "Sinh viên", "Sinh viên tham gia lớp học và dự án."),
    ):
        role, _ = GlobalRole.objects.get_or_create(
            code=code, defaults={"name": name, "description": description}
        )
        roles[code] = role
    return roles


@pytest.fixture
def make_user(seed_global_roles):
    from allauth.account.models import EmailAddress

    from apps.accounts.models import AccountStatus, User, UserGlobalRole

    def _create(
        *,
        email: str | None = None,
        username: str | None = None,
        password: str = "StrongPass123!",
        roles: tuple[str, ...] = ("STUDENT",),
        status: str = AccountStatus.ACTIVE,
        verified: bool = True,
        first_name: str = "An",
        last_name: str = "Nguyen",
        student_id: str | None = None,
    ):
        suffix = uuid4().hex[:8]
        resolved_email = email or f"user_{suffix}@example.edu.vn"
        resolved_username = username or f"user_{suffix}"
        primary_role = roles[0] if roles else "STUDENT"
        user = User.objects.create_user(
            email=resolved_email,
            username=resolved_username,
            password=password,
            account_status=status,
            student_id=student_id,
            first_name=first_name,
            last_name=last_name,
            global_role_code=primary_role,
        )
        if verified:
            EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
        for role_code in roles[1:]:
            UserGlobalRole.objects.get_or_create(user=user, role=seed_global_roles[role_code])
        return user

    return _create


@pytest.fixture
def make_access_token():
    from apps.accounts.models import UserSession
    from apps.authentication.adapters.session_tokens import FamilyRefreshToken, token_expiry

    def _issue(user):
        family = uuid4()
        refresh = FamilyRefreshToken.for_user(user)
        refresh["family_id"] = str(family)
        refresh["family_exp"] = refresh["exp"]
        raw_refresh = str(refresh)
        session = UserSession.objects.create(
            user=user,
            token_family=family,
            refresh_token_hash=hashlib.sha256(raw_refresh.encode()).hexdigest(),
            expires_at=token_expiry(refresh),
            ip_address="127.0.0.1",
            user_agent="pytest",
        )
        access = refresh.access_token
        access["sid"] = str(session.pk)
        access["family_id"] = str(family)
        return str(access), session

    return _issue


@pytest.fixture
def auth_client_for(make_access_token):
    def _client(user):
        access, _session = make_access_token(user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        client.access_token = access
        client.user = user
        return client

    return _client
