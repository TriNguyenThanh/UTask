"""Initial Identity schema for UTask Core Modular Monolith."""

import uuid

import django.db.models.deletion
import django.db.models.functions.text
from django.conf import settings
from django.db import migrations, models

import apps.accounts.managers


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="User",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("email", models.EmailField(max_length=255)),
                ("username", models.CharField(max_length=100)),
                (
                    "password",
                    models.CharField(db_column="password_hash", max_length=255),
                ),
                (
                    "last_login",
                    models.DateTimeField(blank=True, db_column="last_login_at", null=True),
                ),
                ("student_id", models.CharField(blank=True, max_length=50, null=True)),
                (
                    "account_status",
                    models.CharField(
                        choices=[
                            ("PENDING_ACTIVATION", "Pending activation"),
                            ("ACTIVE", "Active"),
                            ("SUSPENDED", "Suspended"),
                        ],
                        default="ACTIVE",
                        max_length=20,
                    ),
                ),
                (
                    "last_login_ip",
                    models.CharField(blank=True, max_length=45, null=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "users",
                "indexes": [
                    models.Index(
                        condition=models.Q(("deleted_at__isnull", True)),
                        fields=["account_status"],
                        name="idx_users_account_status",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("email",), name="uq_users_email"),
                    models.UniqueConstraint(fields=("username",), name="uq_users_username"),
                    models.UniqueConstraint(
                        condition=models.Q(("student_id__isnull", False)),
                        fields=("student_id",),
                        name="uq_users_student_id",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            (
                                "account_status__in",
                                ["PENDING_ACTIVATION", "ACTIVE", "SUSPENDED"],
                            )
                        ),
                        name="chk_user_status",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            (
                                "email",
                                django.db.models.functions.text.Lower(
                                    django.db.models.functions.text.Trim(models.F("email"))
                                ),
                            ),
                            models.Q(("email", ""), _negated=True),
                        ),
                        name="chk_user_email_normalized",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            (
                                "username",
                                django.db.models.functions.text.Lower(
                                    django.db.models.functions.text.Trim(models.F("username"))
                                ),
                            ),
                            models.Q(("username", ""), _negated=True),
                        ),
                        name="chk_user_username_normalized",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("student_id__isnull", True),
                            models.Q(
                                (
                                    "student_id",
                                    django.db.models.functions.text.Upper(
                                        django.db.models.functions.text.Trim(models.F("student_id"))
                                    ),
                                ),
                                models.Q(("student_id", ""), _negated=True),
                            ),
                            _connector="OR",
                        ),
                        name="chk_user_student_id_normalized",
                    ),
                ],
            },
            managers=[
                ("objects", apps.accounts.managers.UserManager()),
            ],
        ),
        migrations.CreateModel(
            name="GlobalRole",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "code",
                    models.CharField(
                        choices=[
                            ("SYSTEM_ADMIN", "System administrator"),
                            ("TEACHER", "Teacher"),
                            ("STUDENT", "Student"),
                        ],
                        max_length=50,
                    ),
                ),
                ("name", models.CharField(max_length=100)),
                ("description", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "global_roles",
                "constraints": [
                    models.UniqueConstraint(fields=("code",), name="uq_global_roles_code"),
                    models.CheckConstraint(
                        condition=models.Q(("code__in", ["SYSTEM_ADMIN", "TEACHER", "STUDENT"])),
                        name="chk_global_role_code",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("actor_id", models.CharField(blank=True, max_length=100, null=True)),
                ("action", models.CharField(max_length=60)),
                (
                    "target_user_id",
                    models.CharField(blank=True, max_length=100, null=True),
                ),
                ("ip_address", models.CharField(max_length=45)),
                ("user_agent", models.TextField()),
                ("details", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "audit_logs",
                "indexes": [
                    models.Index(fields=["-created_at"], name="idx_audit_logs_created_at"),
                    models.Index(
                        condition=models.Q(("target_user_id__isnull", False)),
                        fields=["target_user_id", "-created_at"],
                        name="idx_audit_logs_target_user",
                    ),
                    models.Index(
                        condition=models.Q(("actor_id__isnull", False)),
                        fields=["actor_id", "-created_at"],
                        name="idx_audit_logs_actor",
                    ),
                    models.Index(fields=["action", "-created_at"], name="idx_audit_logs_action"),
                ],
            },
        ),
        migrations.CreateModel(
            name="UserProfile",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("first_name", models.CharField(default="", max_length=100)),
                ("last_name", models.CharField(default="", max_length=100)),
                (
                    "display_name",
                    models.CharField(blank=True, default="", max_length=200),
                ),
                ("avatar_url", models.CharField(blank=True, max_length=500, null=True)),
                (
                    "phone_number",
                    models.CharField(blank=True, max_length=20, null=True),
                ),
                ("bio", models.TextField(blank=True, null=True)),
                (
                    "github_username",
                    models.CharField(blank=True, max_length=100, null=True),
                ),
                (
                    "academic_year",
                    models.CharField(blank=True, max_length=20, null=True),
                ),
                (
                    "faculty",
                    models.CharField(blank=True, default="CNTT", max_length=100, null=True),
                ),
                (
                    "timezone",
                    models.CharField(default="Asia/Ho_Chi_Minh", max_length=50),
                ),
                ("preferences", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        db_column="user_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "user_profiles",
                "indexes": [
                    models.Index(
                        django.db.models.functions.text.Lower("github_username"),
                        condition=models.Q(("github_username__isnull", False)),
                        name="idx_profiles_github_user",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="UserGlobalRole",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("assigned_at", models.DateTimeField(auto_now_add=True)),
                (
                    "assigned_by_user",
                    models.ForeignKey(
                        blank=True,
                        db_column="assigned_by_user_id",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assigned_global_roles",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "role",
                    models.ForeignKey(
                        db_column="role_id",
                        db_index=False,
                        on_delete=django.db.models.deletion.RESTRICT,
                        related_name="user_assignments",
                        to="accounts.globalrole",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        db_column="user_id",
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="global_role_assignments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "user_global_roles",
                "indexes": [models.Index(fields=["role"], name="idx_user_global_roles_role_id")],
                "constraints": [
                    models.UniqueConstraint(fields=("user", "role"), name="uq_user_global_role")
                ],
            },
        ),
        migrations.CreateModel(
            name="UserSession",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("token_family", models.UUIDField()),
                ("refresh_token_hash", models.CharField(max_length=64)),
                ("refresh_jti", models.CharField(blank=True, max_length=255, null=True)),
                ("is_revoked", models.BooleanField(default=False)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "revoked_reason",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("LOGOUT", "Logout"),
                            ("LOGOUT_ALL", "Logout all sessions"),
                            ("ROTATED", "Refresh token rotated"),
                            ("REPLAY_ATTACK", "Refresh token replay detected"),
                            ("ADMIN_REVOKED", "Revoked by administrator"),
                            ("PASSWORD_CHANGED", "Password changed"),
                        ],
                        max_length=100,
                        null=True,
                    ),
                ),
                ("ip_address", models.CharField(max_length=45)),
                ("user_agent", models.TextField()),
                (
                    "device_name",
                    models.CharField(default="Unknown Device", max_length=100),
                ),
                ("expires_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        db_column="user_id",
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sessions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "user_sessions",
                "indexes": [
                    models.Index(
                        fields=["user", "is_revoked", "expires_at"],
                        name="idx_sessions_user_active",
                    ),
                    models.Index(fields=["token_family"], name="idx_sessions_token_family"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("refresh_token_hash",),
                        name="uq_sessions_refresh_token_hash",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("is_revoked", False)),
                        fields=("token_family",),
                        name="uq_session_family_live",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("expires_at__gt", models.F("created_at"))),
                        name="chk_session_expiry",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                ("is_revoked", True),
                                ("revoked_at__isnull", False),
                                ("revoked_reason__isnull", False),
                            ),
                            models.Q(
                                ("is_revoked", False),
                                ("revoked_at__isnull", True),
                                ("revoked_reason__isnull", True),
                            ),
                            _connector="OR",
                        ),
                        name="chk_session_revocation",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("revoked_reason__isnull", True),
                            (
                                "revoked_reason__in",
                                [
                                    "LOGOUT",
                                    "LOGOUT_ALL",
                                    "ROTATED",
                                    "REPLAY_ATTACK",
                                    "ADMIN_REVOKED",
                                    "PASSWORD_CHANGED",
                                ],
                            ),
                            _connector="OR",
                        ),
                        name="chk_session_revoked_reason",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="EmailChangeRequest",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("new_email", models.EmailField(max_length=255)),
                ("token_hash", models.CharField(max_length=64)),
                ("expires_at", models.DateTimeField()),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        db_column="user_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="email_change_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "email_change_requests",
                "indexes": [
                    models.Index(
                        condition=models.Q(("consumed_at__isnull", True)),
                        fields=["user", "created_at"],
                        name="idx_email_change_user_pending",
                    ),
                    models.Index(fields=["expires_at"], name="idx_email_change_expires_at"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("token_hash",), name="uq_email_change_token_hash"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            (
                                "new_email",
                                django.db.models.functions.text.Lower(
                                    django.db.models.functions.text.Trim(models.F("new_email"))
                                ),
                            ),
                            models.Q(("new_email", ""), _negated=True),
                        ),
                        name="chk_email_change_normalized",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("expires_at__gt", models.F("created_at"))),
                        name="chk_email_change_expiry",
                    ),
                ],
            },
        ),
    ]
