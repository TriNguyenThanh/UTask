"""One-use, encrypted PKCE consent; provider calls never hold database locks."""

import base64
import hashlib
import hmac
import secrets
from datetime import timedelta

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ParseError

from infrastructure.github_oauth import GitHubOAuthClient, GitHubOAuthUnavailable

from .errors import (
    GitHubAccountSwitchRequiresUnlink,
    GitHubIdentityInUse,
    StaleGitHubVerification,
)
from .models import GitHubConsentGeneration, GitHubPendingConsent
from .services import link_verified_account
from .validation import validate_user_id

CONSENT_TTL = 600
NONCE_COOKIE = "utask_github_consent"


class ConsentConflict(APIException):
    status_code = 409
    default_detail = "Liên kết đã thay đổi. Hãy unlink hoặc bắt đầu consent mới."
    default_code = "GITHUB_CONSENT_CONFLICT"


def consent_cipher():
    try:
        return Fernet(settings.INTEGRATION_CONSENT_KEY.encode("ascii"))
    except (ValueError, TypeError, AttributeError, UnicodeError):
        raise GitHubOAuthUnavailable() from None


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def session_binding(bearer):
    # Identity /users/me exposes no session ID. Bind the exact verified access
    # bearer, so token refresh during consent requires a new flow.
    consent_cipher()
    return hmac.new(
        settings.INTEGRATION_CONSENT_KEY.encode("ascii"),
        bearer.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def lock_generation(user_id):
    row, _ = GitHubConsentGeneration.objects.get_or_create(user_id=user_id)
    return GitHubConsentGeneration.objects.select_for_update().get(pk=row.pk)


def start_consent(*, user_id, bearer):
    user_id = validate_user_id(user_id)
    cipher = consent_cipher()
    state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    url = GitHubOAuthClient().authorization_url(
        state=state, code_challenge=challenge.rstrip(b"=").decode("ascii")
    )
    expires_at = timezone.now() + timedelta(seconds=CONSENT_TTL)
    with transaction.atomic():
        generation = lock_generation(user_id)
        generation.generation += 1
        generation.save(update_fields=["generation"])
        # Only the latest consent is usable. Drop its predecessor's verifier.
        GitHubPendingConsent.objects.filter(user_id=user_id, consumed_at__isnull=True).update(
            consumed_at=timezone.now(), encrypted_verifier=""
        )
        GitHubPendingConsent.objects.create(
            state_hash=digest(state),
            user_id=user_id,
            session_hash=session_binding(bearer),
            nonce_hash=digest(nonce),
            generation=generation.generation,
            encrypted_verifier=cipher.encrypt(verifier.encode("ascii")).decode("ascii"),
            expires_at=expires_at,
        )
    return {"authorization_url": url, "expires_at": expires_at.isoformat()}, nonce


def consume_consent(*, user_id, bearer, state, nonce):
    cipher = consent_cipher()
    if not isinstance(nonce, str) or not 20 <= len(nonce) <= 256:
        raise ParseError("Consent không hợp lệ hoặc đã hết hạn.")
    with transaction.atomic():
        generation = lock_generation(user_id)
        pending = (
            GitHubPendingConsent.objects.select_for_update()
            .filter(state_hash=digest(state), user_id=user_id)
            .first()
        )
        if (
            pending is None
            or pending.consumed_at is not None
            or pending.expires_at <= timezone.now()
            or pending.generation != generation.generation
            or not hmac.compare_digest(pending.session_hash, session_binding(bearer))
            or not hmac.compare_digest(pending.nonce_hash, digest(nonce))
        ):
            raise ParseError("Consent không hợp lệ hoặc đã hết hạn.")
        encrypted = pending.encrypted_verifier
        pending.consumed_at = timezone.now()
        pending.encrypted_verifier = ""
        pending.save(update_fields=["consumed_at", "encrypted_verifier"])
    # Consume commits before exchange, including timeout or decryption failure.
    try:
        verifier = cipher.decrypt(encrypted.encode("ascii")).decode("ascii")
    except (InvalidToken, UnicodeError, ValueError):
        raise GitHubOAuthUnavailable() from None
    return pending, verifier


def complete_consent(*, user_id, bearer, state, code, nonce):
    user_id = validate_user_id(user_id)
    pending, verifier = consume_consent(user_id=user_id, bearer=bearer, state=state, nonce=nonce)
    github_user_id, github_username = GitHubOAuthClient().verify(code=code, verifier=verifier)
    with transaction.atomic():
        generation = lock_generation(user_id)
        if generation.generation != pending.generation or pending.expires_at <= timezone.now():
            raise ConsentConflict()
        try:
            return link_verified_account(
                user_id=user_id,
                github_user_id=github_user_id,
                github_username=github_username,
                verified_at=timezone.now(),
            )
        except (GitHubIdentityInUse, GitHubAccountSwitchRequiresUnlink, StaleGitHubVerification):
            raise ConsentConflict() from None
