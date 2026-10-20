"""Leased durable work. Broker messages never contain provider tokens or raw webhooks."""

import random
from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.github_accounts.credentials import decrypt_secret, require_enabled

from .models import GitHubJob


class StaleJobLease(RuntimeError):
    pass


def run_job(job_id):
    now = timezone.now()
    with transaction.atomic():
        row = GitHubJob.objects.select_for_update().filter(pk=job_id).first()
        if row is None or row.status in {"DONE", "IGNORED", "FAILED"}:
            return
        if row.kind != "REVOKE_TOKEN":
            require_enabled()
        if row.status == "PROCESSING" and row.lease_until > now:
            return
        if row.available_at > now:
            return
        if row.attempts >= 5:
            row.status, row.claim, row.lease_until, row.last_error = (
                "FAILED",
                None,
                None,
                "RETRY_EXHAUSTED",
            )
            row.save()
            return
        row.status = "PROCESSING"
        row.attempts += 1
        row.version += 1
        row.claim = uuid4()
        row.lease_until = now + timedelta(seconds=60)
        row.save()
        claim, version, payload, kind = row.claim, row.version, row.payload, row.kind
        secret_expires_at = row.secret_expires_at
    try:
        if kind == "REVOKE_TOKEN":
            from infrastructure.github_app import GitHubAppClient

            if secret_expires_at is not None and secret_expires_at <= timezone.now():
                _complete(job_id, claim, version)
                return
            if payload["client_id"] != settings.INTEGRATION_GITHUB_CLIENT_ID:
                raise ValueError("REGISTRATION_CHANGED")
            if secret_expires_at is None or secret_expires_at > timezone.now():
                from infrastructure.github_app import GitHubNotFound

                try:
                    GitHubAppClient().revoke(
                        access_token=decrypt_secret(payload["encrypted_token"])
                    )
                except GitHubNotFound:
                    pass  # Already revoked or no longer present at GitHub.
        elif kind == "WEBHOOK":
            from apps.github_installations.services import invalidate_installation

            # Metadata updates and receipt completion commit atomically under the lease.
            with transaction.atomic():
                current = GitHubJob.objects.select_for_update().get(pk=job_id)
                if (
                    current.claim != claim
                    or current.version != version
                    or current.lease_until <= timezone.now()
                ):
                    return
                invalidate_installation(
                    installation_id=payload["installation_id"],
                    event=payload["action"],
                    removed_repository_ids=payload.get("removed_repository_ids", []),
                )
                if not _complete(job_id, claim, version):
                    raise StaleJobLease()
            return
        else:
            raise ValueError("UNKNOWN_JOB")
    except Exception as exc:
        # Class names only; exception text may contain request credentials.
        status = getattr(exc, "status_code", 503)
        retryable = status in {429, 500, 502, 503, 504} and not isinstance(
            exc, (ValueError, KeyError)
        )
        delay = min(300, 2**row.attempts + random.uniform(0, 1))
        retry_after = getattr(exc, "wait", None)
        if retry_after is not None:
            delay = max(delay, float(retry_after))
        with transaction.atomic():
            current = GitHubJob.objects.select_for_update().get(pk=job_id)
            if (
                current.claim != claim
                or current.version != version
                or current.lease_until <= timezone.now()
            ):
                return
            current.status = "PENDING" if retryable and current.attempts < 5 else "FAILED"
            current.claim, current.lease_until = None, None
            current.available_at = timezone.now() + timedelta(seconds=delay)
            current.last_error = type(exc).__name__[:80]
            current.save()
        return
    _complete(job_id, claim, version)


def _complete(job_id, claim, version):
    return GitHubJob.objects.filter(
        pk=job_id, claim=claim, version=version, lease_until__gt=timezone.now()
    ).update(
        status="DONE",
        completed_at=timezone.now(),
        payload={},
        claim=None,
        lease_until=None,
        last_error="",
    )


def dispatch_pending():
    from .tasks import process_github_job

    now = timezone.now()
    rows = (
        GitHubJob.objects.filter(
            Q(status="PENDING", available_at__lte=now)
            | Q(status="PROCESSING", lease_until__lte=now)
        )
        .order_by("available_at")
        .values_list("pk", flat=True)[:100]
    )
    sent = 0
    for pk in rows:
        try:
            process_github_job.apply_async(args=[pk], queue="integration")
            sent += 1
        except Exception:
            break  # Database rows remain pending; the next scan retries broker delivery.
    return sent


def cleanup_deliveries():
    now = timezone.now()
    count = (
        GitHubJob.objects.filter(
            kind="WEBHOOK",
            status__in=["DONE", "IGNORED"],
            completed_at__lt=now - timedelta(days=30),
        )
        .exclude(payload={})
        .update(payload={})
    )
    # Keep deduplication fingerprints after payload removal, including failed secret jobs.
    GitHubJob.objects.filter(kind="REVOKE_TOKEN", secret_expires_at__lte=now).exclude(
        payload={}
    ).update(payload={})
    return count


def replay_job(job_id):
    with transaction.atomic():
        row = GitHubJob.objects.select_for_update().get(pk=job_id)
        if row.status != "FAILED" or not row.payload:
            raise ValueError("Only failed jobs with a retained payload can be replayed")
        row.status, row.attempts, row.claim, row.lease_until = "PENDING", 0, None, None
        row.version += 1
        row.available_at = timezone.now()
        row.last_error = ""
        row.save()
