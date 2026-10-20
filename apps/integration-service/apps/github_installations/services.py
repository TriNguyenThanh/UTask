"""Installation consent binds actor, browser and current provider credential."""

import hmac
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ParseError

from apps.github_accounts.consent import (
    CONSENT_TTL,
    ConsentConflict,
    digest,
    lock_generation,
    session_binding,
)
from apps.github_accounts.credentials import assert_access_current, get_access_token
from apps.github_accounts.validation import GITHUB_ID_PATTERN
from infrastructure.github_app import (
    GitHubAccessDenied,
    GitHubAppClient,
    GitHubAppReauthorizationRequired,
    GitHubNotFound,
)
from infrastructure.github_oauth import GitHubOAuthUnavailable

from .models import GitHubInstallation, GitHubInstallationGeneration, GitHubPendingInstallation

NONCE_COOKIE = "utask_github_installation"


def provider_call(user_id, access, call, *args, **kwargs):
    try:
        return call(*args, **kwargs)
    except GitHubAppReauthorizationRequired:
        from apps.github_accounts.credentials import mark_reauthorization_required

        mark_reauthorization_required(user_id=user_id, access=access)
        raise


def enabled_client():
    client = GitHubAppClient()
    client._configuration()
    return client


def lock_installation_generation(user_id):
    row, _ = GitHubInstallationGeneration.objects.get_or_create(user_id=user_id)
    return GitHubInstallationGeneration.objects.select_for_update().get(pk=row.pk)


def check_pending_current(user_id, pending, access):
    generation = lock_generation(user_id)
    installation_generation = lock_installation_generation(user_id)
    assert_access_current(user_id=user_id, access=access)
    if (
        generation.generation != pending.generation
        or installation_generation.generation != pending.installation_generation
        or pending.expires_at <= timezone.now()
    ):
        raise ConsentConflict()


def start_installation(*, user_id, bearer):
    client = enabled_client()
    access = get_access_token(user_id=user_id)
    state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    url = client.installation_url(state=state)
    expires_at = timezone.now() + timedelta(seconds=CONSENT_TTL)
    with transaction.atomic():
        generation = lock_generation(user_id)
        installation_generation = lock_installation_generation(user_id)
        installation_generation.generation += 1
        installation_generation.save(update_fields=["generation"])
        assert_access_current(user_id=user_id, access=access)
        GitHubPendingInstallation.objects.filter(user_id=user_id, consumed_at__isnull=True).update(
            consumed_at=timezone.now()
        )
        GitHubPendingInstallation.objects.create(
            state_hash=digest(state),
            user_id=user_id,
            session_hash=session_binding(bearer),
            nonce_hash=digest(nonce),
            generation=generation.generation,
            credential_version=access.version,
            installation_generation=installation_generation.generation,
            expires_at=expires_at,
        )
    return {"installation_url": url, "expires_at": expires_at.isoformat()}, nonce


def consume_installation(*, user_id, bearer, state, nonce):
    if not isinstance(nonce, str) or not 20 <= len(nonce) <= 256:
        raise ParseError("Consent installation không hợp lệ hoặc đã hết hạn.")
    with transaction.atomic():
        generation = lock_generation(user_id)
        installation_generation = lock_installation_generation(user_id)
        pending = (
            GitHubPendingInstallation.objects.select_for_update()
            .filter(state_hash=digest(state), user_id=user_id)
            .first()
        )
        if (
            pending is None
            or pending.consumed_at is not None
            or pending.expires_at <= timezone.now()
            or pending.generation != generation.generation
            or pending.installation_generation != installation_generation.generation
            or not hmac.compare_digest(pending.session_hash, session_binding(bearer))
            or not hmac.compare_digest(pending.nonce_hash, digest(nonce))
        ):
            raise ParseError("Consent installation không hợp lệ hoặc đã hết hạn.")
        pending.consumed_at = timezone.now()
        pending.save(update_fields=["consumed_at"])
    return pending


def live_installation(client, token, installation_id):
    page = 1
    while page <= 10:
        data = client.installations(token, page=page, per_page=100)
        for item in data["items"]:
            if item["installation_id"] == installation_id:
                if (
                    item["app_id"] != str(settings.INTEGRATION_GITHUB_APP_ID)
                    or item["suspended_at"] is not None
                ):
                    raise GitHubAccessDenied()
                return item
        next_page = data["next_page"]
        if next_page is None:
            raise GitHubNotFound()
        if next_page <= page:
            raise GitHubOAuthUnavailable()
        page = next_page
    raise GitHubOAuthUnavailable()


def remember_installation(item):
    suspended_at = parse_datetime(item["suspended_at"]) if item["suspended_at"] else None
    row, _ = GitHubInstallation.objects.update_or_create(
        installation_id=item["installation_id"],
        defaults={
            "app_id": item["app_id"],
            "account_id": item["account"]["id"],
            "account_login": item["account"]["login"],
            "account_type": item["account"]["type"],
            "repository_selection": item["repository_selection"],
            "suspended_at": suspended_at,
            "status": "SUSPENDED" if suspended_at else "ACTIVE",
        },
    )
    return row


def complete_installation(*, user_id, bearer, state, nonce, installation_id, setup_action):
    client = enabled_client()
    pending = consume_installation(user_id=user_id, bearer=bearer, state=state, nonce=nonce)
    access = get_access_token(user_id=user_id)
    if access.version != pending.credential_version or access.generation != pending.generation:
        raise ConsentConflict()
    if setup_action == "request":
        with transaction.atomic():
            check_pending_current(user_id, pending, access)
        return {"status": "PENDING_APPROVAL", "installation_id": installation_id}
    item = provider_call(
        user_id, access, live_installation, client, access.access_token, installation_id
    )
    provider_call(
        user_id,
        access,
        client.repositories,
        access.access_token,
        installation_id,
        page=1,
        per_page=1,
    )
    with transaction.atomic():
        check_pending_current(user_id, pending, access)
        remember_installation(item)
    return {"status": "ACTIVE", **item}


def list_installations(*, user_id, page, per_page):
    client = enabled_client()
    access = get_access_token(user_id=user_id)
    data = provider_call(
        user_id, access, client.installations, access.access_token, page=page, per_page=per_page
    )
    data["items"] = [
        item
        for item in data["items"]
        if item["app_id"] == str(settings.INTEGRATION_GITHUB_APP_ID)
        and item["suspended_at"] is None
    ]
    assert_access_current(user_id=user_id, access=access)
    return data


def list_repositories(*, user_id, installation_id, page, per_page):
    client = enabled_client()
    access = get_access_token(user_id=user_id)
    provider_call(user_id, access, live_installation, client, access.access_token, installation_id)
    data = provider_call(
        user_id,
        access,
        client.repositories,
        access.access_token,
        installation_id,
        page=page,
        per_page=per_page,
    )
    assert_access_current(user_id=user_id, access=access)
    return data


def invalidate_installation(*, installation_id, event, removed_repository_ids=()):
    """Webhook invalidates metadata only; repository grants are never cached."""
    if not isinstance(installation_id, str) or not re.fullmatch(GITHUB_ID_PATTERN, installation_id):
        raise ValueError("Invalid installation ID")
    statuses = {
        "created": "STALE",
        "deleted": "DELETED",
        "suspend": "SUSPENDED",
        "unsuspend": "STALE",
        "new_permissions_accepted": "STALE",
        "repositories_added": "STALE",
        "repositories_removed": "STALE",
    }
    if event not in statuses:
        raise ValueError("Invalid installation event")
    with transaction.atomic():
        from apps.github_connections.services import invalidate_connections

        invalidate_connections(
            installation_id=installation_id,
            event=event,
            removed_repository_ids=removed_repository_ids,
        )
        row = GitHubInstallation.objects.select_for_update().filter(pk=installation_id).first()
        if row is None:
            return None
        row.status = statuses[event]
        row.source_version += 1
        row.save(update_fields=["status", "source_version", "updated_at"])
        return row
