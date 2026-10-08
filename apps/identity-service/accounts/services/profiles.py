from django.db import transaction

from accounts.models import User
from accounts.services.account_access import account_audit, lock_accounts
from messaging.outbox import emit_user


def public_users():
    return (
        User.objects.filter(deleted_at__isnull=True)
        .select_related("profile")
        .prefetch_related("global_role_assignments__role", "emailaddress_set")
    )


def update_profile(request, changes):
    with transaction.atomic():
        user = lock_accounts(request)[request.user.pk]
        profile = user.profile
        changed = [field for field, value in changes.items() if getattr(profile, field) != value]
        if changed:
            for field in changed:
                setattr(profile, field, changes[field])
            profile.save(update_fields=(*changed, "updated_at"))
            profile.refresh_from_db()  # PostgreSQL display_name trigger is authoritative.
            account_audit(request, user, "PROFILE_UPDATED", fields=changed)
            emit_user(user, "identity.user.updated")
        return profile
