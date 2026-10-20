"""Encrypted user credentials and fenced refresh; HTTP never holds row locks."""

import json
import re
from dataclasses import dataclass, field
from datetime import timedelta
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException

from infrastructure.github_oauth import GitHubOAuthUnavailable

from .models import GitHubAccount, GitHubCredential
from .validation import validate_user_id


class ReauthorizationRequired(APIException):
    status_code = 409
    default_code = "GITHUB_REAUTH_REQUIRED"
    default_detail = "Hãy cấp quyền GitHub App lại để tiếp tục."


class RefreshInProgress(APIException):
    status_code = 409
    default_code = "GITHUB_REFRESH_IN_PROGRESS"
    default_detail = "Quyền GitHub đang được làm mới. Hãy thử lại."


@dataclass(frozen=True)
class CredentialAccess:
    access_token: str = field(repr=False)
    version: int
    generation: int


def credential_cipher():
    try:
        keys = settings.INTEGRATION_CREDENTIAL_KEYS
        if isinstance(keys, str):
            keys = json.loads(keys)
        if not isinstance(keys, list) or not keys:
            raise ValueError()
        if any(not isinstance(key, str) or key == settings.INTEGRATION_CONSENT_KEY for key in keys):
            raise ValueError()
        return MultiFernet([Fernet(key.encode("ascii")) for key in keys])
    except (ValueError, TypeError, AttributeError, UnicodeError):
        raise GitHubOAuthUnavailable() from None


def encrypt_secret(value):
    if not isinstance(value, str) or not value or len(value) > 8192:
        raise GitHubOAuthUnavailable()
    try:
        return credential_cipher().encrypt(value.encode("ascii")).decode("ascii")
    except UnicodeError:
        raise GitHubOAuthUnavailable() from None


def decrypt_secret(value):
    try:
        return credential_cipher().decrypt(value.encode("ascii")).decode("ascii")
    except (InvalidToken, ValueError, TypeError, AttributeError, UnicodeError):
        raise GitHubOAuthUnavailable() from None


def require_enabled():
    if not settings.INTEGRATION_GITHUB_APP_ENABLED:
        raise GitHubOAuthUnavailable()
    app_id = settings.INTEGRATION_GITHUB_APP_ID
    if not isinstance(app_id, str) or not re.fullmatch(r"[1-9][0-9]{0,99}", app_id):
        raise GitHubOAuthUnavailable()
    credential_cipher()


def retire_token(*, encrypted_token, expires_at):
    """Persist revocation intent inside the caller's transaction, not a grant-wide revoke."""
    from apps.github_jobs.models import GitHubJob

    if encrypted_token:
        GitHubJob.objects.create(
            kind="REVOKE_TOKEN",
            payload={
                "encrypted_token": encrypted_token,
                "client_id": settings.INTEGRATION_GITHUB_CLIENT_ID,
            },
            secret_expires_at=expires_at,
        )


def store_credential(*, user_id, identity):
    """Caller holds actor generation and commits this together with the account mapping."""
    encrypted_access = encrypt_secret(identity.access_token)
    encrypted_refresh = encrypt_secret(identity.refresh_token)
    current = GitHubCredential.objects.select_for_update().filter(user_id=user_id).first()
    version = current.version + 1 if current else 1
    if current:
        retire_token(
            encrypted_token=current.encrypted_access_token, expires_at=current.refresh_expires_at
        )
    return GitHubCredential.objects.update_or_create(
        user_id=user_id,
        defaults={
            "github_user_id": identity.github_user_id,
            "app_id": str(settings.INTEGRATION_GITHUB_APP_ID),
            "encrypted_access_token": encrypted_access,
            "encrypted_refresh_token": encrypted_refresh,
            "expires_at": identity.expires_at,
            "refresh_expires_at": identity.refresh_expires_at,
            "version": version,
            "status": GitHubCredential.Status.ACTIVE,
            "refresh_claim": None,
            "refresh_started_at": None,
        },
    )[0]


def revoke_credential(*, user_id, provider_revoked=False):
    """Caller holds generation; retained secrets are usable only by a revocation job."""
    from apps.github_connections.services import disconnect_for_user

    disconnect_for_user(user_id)
    row = GitHubCredential.objects.select_for_update().filter(user_id=user_id).first()
    if row is None or row.status == GitHubCredential.Status.REVOKED:
        return
    if not provider_revoked:
        retire_token(encrypted_token=row.encrypted_access_token, expires_at=row.refresh_expires_at)
    row.status = GitHubCredential.Status.REVOKED
    row.version += 1
    row.encrypted_access_token = ""
    row.encrypted_refresh_token = ""
    row.refresh_claim = None
    row.refresh_started_at = None
    row.save()


def authorization_status(*, user_id, account):
    if account is None:
        return "NOT_AUTHORIZED"
    if account.status == "REVOKED":
        return "REVOKED"
    if not settings.INTEGRATION_GITHUB_APP_ENABLED:
        return "NOT_AUTHORIZED"
    row = GitHubCredential.objects.filter(user_id=user_id).first()
    if row is None or row.app_id != str(settings.INTEGRATION_GITHUB_APP_ID):
        return "NOT_AUTHORIZED"
    if row.status in {"ACTIVE", "REFRESHING"} and row.refresh_expires_at > timezone.now():
        return "ACTIVE"
    return "REVOKED" if row.status == "REVOKED" else "REAUTH_REQUIRED"


def assert_access_current(*, user_id, access):
    from .consent import lock_generation

    with transaction.atomic():
        generation = lock_generation(user_id)
        row = GitHubCredential.objects.filter(user_id=user_id).first()
        if (
            generation.generation != access.generation
            or row is None
            or row.version != access.version
            or row.status != "ACTIVE"
            or row.app_id != str(settings.INTEGRATION_GITHUB_APP_ID)
            or row.expires_at <= timezone.now()
        ):
            raise ReauthorizationRequired()


def get_access_token(*, user_id):
    from infrastructure.github_app import GitHubAppClient

    from .consent import lock_generation

    require_enabled()
    user_id = validate_user_id(user_id)
    error = None
    with transaction.atomic():
        generation = lock_generation(user_id)
        row = GitHubCredential.objects.select_for_update().filter(user_id=user_id).first()
        account = GitHubAccount.objects.filter(user_id=user_id, status="LINKED").first()
        if (
            row is None
            or account is None
            or row.github_user_id != account.github_user_id
            or row.app_id != str(settings.INTEGRATION_GITHUB_APP_ID)
            or row.status in {"REAUTH_REQUIRED", "REVOKED"}
        ):
            raise ReauthorizationRequired()
        now = timezone.now()
        if row.status == "REFRESHING":
            if row.refresh_started_at > now - timedelta(seconds=30):
                raise RefreshInProgress()
            row.status = "REAUTH_REQUIRED"
            row.refresh_claim = None
            row.refresh_started_at = None
            row.version += 1
            row.save()
            error = ReauthorizationRequired()
        elif row.refresh_expires_at <= now:
            row.status = "REAUTH_REQUIRED"
            row.version += 1
            row.save()
            error = ReauthorizationRequired()
        elif row.expires_at > now + timedelta(seconds=60):
            return CredentialAccess(
                decrypt_secret(row.encrypted_access_token), row.version, generation.generation
            )
        else:
            refresh_token = decrypt_secret(row.encrypted_refresh_token)
            claim = uuid4()
            row.status = "REFRESHING"
            row.refresh_claim = claim
            row.refresh_started_at = now
            row.save()
            expected_version, expected_generation = row.version, generation.generation
    if error:
        raise error
    try:
        pair = GitHubAppClient().refresh(refresh_token=refresh_token)
    except Exception:
        # A response may be lost after GitHub rotated the pair. Never retry this refresh.
        with transaction.atomic():
            lock_generation(user_id)
            GitHubCredential.objects.filter(user_id=user_id, refresh_claim=claim).update(
                status="REAUTH_REQUIRED",
                refresh_claim=None,
                refresh_started_at=None,
                version=expected_version + 1,
            )
        raise ReauthorizationRequired() from None
    conflict = False
    with transaction.atomic():
        generation = lock_generation(user_id)
        row = GitHubCredential.objects.select_for_update().get(user_id=user_id)
        if (
            generation.generation != expected_generation
            or row.version != expected_version
            or row.refresh_claim != claim
            or row.status != "REFRESHING"
        ):
            retire_token(
                encrypted_token=encrypt_secret(pair.access_token),
                expires_at=pair.refresh_expires_at,
            )
            conflict = True
        else:
            row.encrypted_access_token = encrypt_secret(pair.access_token)
            row.encrypted_refresh_token = encrypt_secret(pair.refresh_token)
            row.expires_at = pair.expires_at
            row.refresh_expires_at = pair.refresh_expires_at
            row.version += 1
            row.status = "ACTIVE"
            row.refresh_claim = None
            row.refresh_started_at = None
            row.save()
            access = CredentialAccess(pair.access_token, row.version, generation.generation)
    if conflict:
        raise ReauthorizationRequired()
    return access


def mark_reauthorization_required(*, user_id, access):
    from .consent import lock_generation

    with transaction.atomic():
        generation = lock_generation(user_id)
        if generation.generation == access.generation:
            GitHubCredential.objects.filter(
                user_id=user_id, version=access.version, status="ACTIVE"
            ).update(
                status="REAUTH_REQUIRED",
                version=access.version + 1,
            )
