"""Authenticate raw deliveries before parsing and persist before acknowledging."""

import hashlib
import hmac
import json
import re

from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ParseError, PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.github_accounts.credentials import require_enabled, revoke_credential
from apps.github_accounts.models import (
    GitHubAccount,
    GitHubAuthorizationRevocation,
    GitHubCredential,
    GitHubPendingConsent,
)
from common.api_errors import integration_exception_handler
from infrastructure.github_oauth import GitHubOAuthUnavailable

from .models import GitHubJob

MAX_WEBHOOK_BYTES = 25 * 1024 * 1024


class DeliveryConflict(APIException):
    status_code = 409
    default_code = "GITHUB_DELIVERY_CONFLICT"
    default_detail = "Delivery ID đã được sử dụng cho payload khác."


class PayloadTooLarge(APIException):
    status_code = 413
    default_code = "PAYLOAD_TOO_LARGE"
    default_detail = "Webhook vượt giới hạn 25 MiB."


def positive_id(value):
    if type(value) is not int or value <= 0 or len(str(value)) > 100:
        raise ParseError("ID GitHub không hợp lệ.")
    return str(value)


def normalize_delivery(event, payload):
    if not isinstance(payload, dict):
        raise ParseError("Webhook phải là JSON object.")
    if event == "ping":
        return {}, "DONE"
    if event == "github_app_authorization":
        if payload.get("action") != "revoked":
            return {}, "IGNORED"
        sender = payload.get("sender")
        if not isinstance(sender, dict):
            raise ParseError("Thiếu sender GitHub.")
        return {"github_user_id": positive_id(sender.get("id"))}, "DONE"
    if event not in {"installation", "installation_repositories"}:
        return {}, "IGNORED"
    installation = payload.get("installation")
    if not isinstance(installation, dict):
        raise ParseError("Thiếu installation.")
    installation_id = positive_id(installation.get("id"))
    if str(installation.get("app_id")) != str(settings.INTEGRATION_GITHUB_APP_ID):
        raise PermissionDenied("Webhook không thuộc GitHub App này.")
    action = payload.get("action")
    allowed = (
        {"created", "deleted", "suspend", "unsuspend", "new_permissions_accepted"}
        if event == "installation"
        else {"added", "removed"}
    )
    if not isinstance(action, str) or action not in allowed:
        return {}, "IGNORED"
    removed = payload.get("repositories_removed", [])
    if not isinstance(removed, list) or any(not isinstance(item, dict) for item in removed):
        raise ParseError("Danh sách repository không hợp lệ.")
    return {
        "installation_id": installation_id,
        "action": action if event == "installation" else f"repositories_{action}",
        "removed_repository_ids": [positive_id(item.get("id")) for item in removed],
    }, "PENDING"


def revoke_authorization(github_user_id):
    from apps.github_accounts.consent import lock_generation

    fence, _ = GitHubAuthorizationRevocation.objects.get_or_create(github_user_id=github_user_id)
    fence = GitHubAuthorizationRevocation.objects.select_for_update().get(pk=fence.pk)
    fence.revoked_at = timezone.now()
    fence.save(update_fields=["revoked_at"])
    actors = set(
        GitHubAccount.objects.filter(github_user_id=github_user_id, status="LINKED").values_list(
            "user_id", flat=True
        )
    )
    actors.update(
        GitHubCredential.objects.filter(github_user_id=github_user_id).values_list(
            "user_id", flat=True
        )
    )
    for user_id in sorted(actors, key=str):
        generation = lock_generation(user_id)
        # Actor candidates were read before waiting for the lock. A concurrent
        # unlink/relink may already have switched this actor to another identity.
        still_linked = GitHubAccount.objects.filter(
            user_id=user_id, github_user_id=github_user_id, status="LINKED"
        ).exists()
        still_credential = GitHubCredential.objects.filter(
            user_id=user_id, github_user_id=github_user_id
        ).exists()
        if not still_linked and not still_credential:
            continue
        generation.generation += 1
        generation.save(update_fields=["generation"])
        GitHubPendingConsent.objects.filter(user_id=user_id, consumed_at__isnull=True).update(
            consumed_at=timezone.now(), encrypted_verifier=""
        )
        revoke_credential(user_id=user_id, provider_revoked=True)


def receive_delivery(*, raw, signature, delivery_id, event):
    require_enabled()
    secret = settings.INTEGRATION_GITHUB_WEBHOOK_SECRET
    if not isinstance(secret, str) or not secret:
        raise GitHubOAuthUnavailable()
    if len(raw) > MAX_WEBHOOK_BYTES:
        raise PayloadTooLarge()
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if (
        not isinstance(signature, str)
        or not re.fullmatch(r"sha256=[a-f0-9]{64}", signature)
        or not hmac.compare_digest(expected, signature)
    ):
        raise PermissionDenied("Chữ ký webhook không hợp lệ.")
    if (
        not isinstance(delivery_id, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", delivery_id)
        or not isinstance(event, str)
        or not re.fullmatch(r"[a-z_]{1,80}", event)
    ):
        raise ParseError("Header webhook không hợp lệ.")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        raise ParseError("Webhook phải là JSON hợp lệ.") from None
    normalized, status = normalize_delivery(event, payload)
    fingerprint = hashlib.sha256(event.encode() + b"\0" + raw).hexdigest()
    with transaction.atomic():
        row, created = GitHubJob.objects.get_or_create(
            delivery_id=delivery_id,
            defaults={
                "kind": "WEBHOOK",
                "event": event,
                "payload_hash": fingerprint,
                "payload": normalized,
                "status": status,
                "completed_at": timezone.now() if status in {"DONE", "IGNORED"} else None,
            },
        )
        if row.payload_hash != fingerprint:
            raise DeliveryConflict()
        if created and event == "github_app_authorization" and status == "DONE":
            revoke_authorization(normalized["github_user_id"])
    return row


def webhook_exception_handler(exc, context):
    if isinstance(exc, RequestDataTooBig):
        exc = PayloadTooLarge()
    return integration_exception_handler(exc, context)


class GitHubWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    http_method_names = ["post", "options"]

    def get_exception_handler(self):
        return webhook_exception_handler

    def post(self, request):
        if request.query_params:
            raise ParseError("Webhook không nhận query.")
        if request.content_type != "application/json":
            raise ParseError("Webhook chỉ nhận application/json.")
        row = receive_delivery(
            raw=request.body,
            signature=request.headers.get("X-Hub-Signature-256"),
            delivery_id=request.headers.get("X-GitHub-Delivery"),
            event=request.headers.get("X-GitHub-Event"),
        )
        return Response(
            {"success": True, "data": {"delivery_id": row.delivery_id}},
            status=202,
            headers={"Cache-Control": "no-store"},
        )
