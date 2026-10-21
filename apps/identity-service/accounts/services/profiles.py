from django.db import IntegrityError, transaction
from rest_framework import serializers

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
        profile_changes = dict(changes)
        student_id = profile_changes.pop("student_id", user.student_id)
        student_id_changed = student_id != user.student_id
        changed = [
            field for field, value in profile_changes.items() if getattr(profile, field) != value
        ]
        changed_fields = [*changed]

        if student_id_changed:
            if (
                student_id is not None
                and User.objects.filter(student_id=student_id).exclude(pk=user.pk).exists()
            ):
                raise serializers.ValidationError(
                    {"student_id": "MSSV này đã được gán cho tài khoản khác."}
                )
            try:
                with transaction.atomic():
                    user.student_id = student_id
                    user.save(update_fields=("student_id", "updated_at"))
            except IntegrityError as error:
                if (
                    student_id is None
                    or not User.objects.filter(student_id=student_id).exclude(pk=user.pk).exists()
                ):
                    raise
                raise serializers.ValidationError(
                    {"student_id": "MSSV này đã được gán cho tài khoản khác."}
                ) from error
            changed_fields.append("student_id")

        if changed:
            for field in changed:
                setattr(profile, field, profile_changes[field])
            profile.save(update_fields=(*changed, "updated_at"))
            profile.refresh_from_db()  # PostgreSQL display_name trigger is authoritative.

        if changed_fields:
            account_audit(request, user, "PROFILE_UPDATED", fields=changed_fields)
            emit_user(user, "identity.user.updated")
        return profile
