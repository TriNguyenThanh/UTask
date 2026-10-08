"""Retire duplicate state only after legacy lockouts have expired."""

from django.db import migrations, models
from django.utils import timezone


def transfer_library_state(apps, schema_editor):
    alias = schema_editor.connection.alias
    User = apps.get_model("accounts", "User")
    EmailAddress = apps.get_model("account", "EmailAddress")
    users = User.objects.using(alias)
    # Fail closed rather than inventing Axes attempts or unlocking a live lock.
    # Run this migration during local maintenance, after the 15-minute cooldown.
    if users.filter(account_status="LOCKED", locked_until__gt=timezone.now()).exists():
        raise RuntimeError("Unexpired legacy account locks exist; retry after their cooldown.")

    for user in users.all().iterator():
        addresses = EmailAddress.objects.using(alias).filter(user_id=user.pk)
        # Existing allauth verification (even False) wins over the duplicate flag.
        # Preserve the flag only where there is no matching allauth email record.
        if not addresses.filter(email__iexact=user.email).exists():
            EmailAddress.objects.using(alias).create(
                user_id=user.pk,
                email=user.email,
                verified=user.is_email_verified,
                primary=not addresses.filter(primary=True).exists(),
            )
    # Only expired temporary locks are retired. Suspensions, soft deletes, Axes
    # attempts and session revocations stay untouched.
    users.filter(account_status="LOCKED").update(account_status="ACTIVE")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_idempotencyrecord"),
        ("account", "0009_emailaddress_unique_primary_email"),
    ]

    operations = [
        migrations.RemoveConstraint(model_name="user", name="chk_user_lock_state"),
        migrations.RemoveConstraint(model_name="user", name="chk_login_attempts"),
        migrations.RemoveIndex(model_name="user", name="idx_users_locked_until"),
        # Irreversible: take a database backup before applying; don't invent old counters.
        migrations.RunPython(transfer_library_state),
        migrations.RemoveConstraint(model_name="user", name="chk_user_status"),
        migrations.RemoveField(model_name="user", name="failed_login_attempts"),
        migrations.RemoveField(model_name="user", name="locked_until"),
        migrations.RemoveField(model_name="user", name="is_email_verified"),
        migrations.AlterField(
            model_name="user",
            name="account_status",
            field=models.CharField(
                choices=[
                    ("PENDING_ACTIVATION", "Pending activation"),
                    ("ACTIVE", "Active"),
                    ("SUSPENDED", "Suspended"),
                ],
                default="ACTIVE",
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    account_status__in=["PENDING_ACTIVATION", "ACTIVE", "SUSPENDED"]
                ),
                name="chk_user_status",
            ),
        ),
    ]
