from django.db import IntegrityError, transaction
from django.utils import timezone

from .errors import (
    GitHubAccountSwitchRequiresUnlink,
    GitHubIdentityInUse,
    StaleGitHubVerification,
)
from .models import GitHubAccount
from .validation import validate_user_id, validate_verified_identity


def link_verified_account(*, user_id, github_user_id, github_username, verified_at):
    """Persist an internal adapter's verified identity; this does not verify OAuth."""
    now = timezone.now()
    identity = validate_verified_identity(
        user_id=user_id,
        github_user_id=github_user_id,
        github_username=github_username,
        verified_at=verified_at,
        now=now,
    )
    try:
        with transaction.atomic():
            account, created = GitHubAccount.objects.get_or_create(
                user_id=identity.user_id,
                defaults={
                    "github_user_id": identity.github_user_id,
                    "github_username": identity.github_username,
                    "verified_at": identity.verified_at,
                    "linked_at": now,
                },
            )
            if created:
                return account
            # get_or_create handles concurrent first links; lock and reread existing state.
            account = GitHubAccount.objects.select_for_update().get(pk=account.pk)
            if (
                account.status == GitHubAccount.Status.LINKED
                and account.github_user_id == identity.github_user_id
                and account.github_username == identity.github_username
                and account.verified_at == identity.verified_at
            ):
                return account
            if (
                account.status == GitHubAccount.Status.LINKED
                and account.github_user_id != identity.github_user_id
            ):
                raise GitHubAccountSwitchRequiresUnlink("Unlink the current GitHub account first")
            watermark = account.revoked_at or account.verified_at
            if identity.verified_at <= max(watermark, account.verified_at):
                raise StaleGitHubVerification("A newer GitHub verification is required")
            if account.status == GitHubAccount.Status.REVOKED:
                account.linked_at = timezone.now()
            account.github_user_id = identity.github_user_id
            account.github_username = identity.github_username
            account.verified_at = identity.verified_at
            account.status = GitHubAccount.Status.LINKED
            account.revoked_at = None
            account.source_version += 1
            account.save()
            return account
    except IntegrityError as exc:
        constraint = getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None)
        if constraint == "uq_github_account_active_id":
            raise GitHubIdentityInUse(
                "The GitHub account is already linked to another user"
            ) from exc
        raise


def unlink_github_account(*, user_id):
    """Revoke only this user's binding; repeated revocation leaves its version unchanged."""
    user_id = validate_user_id(user_id)
    with transaction.atomic():
        account = GitHubAccount.objects.select_for_update().filter(user_id=user_id).first()
        if account is None or account.status == GitHubAccount.Status.REVOKED:
            return account
        account.status = GitHubAccount.Status.REVOKED
        account.revoked_at = timezone.now()
        account.source_version += 1
        account.save(update_fields=["status", "revoked_at", "source_version", "updated_at"])
        return account
