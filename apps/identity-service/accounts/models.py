import uuid

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower, Trim, Upper

from accounts.managers import UserManager


class AccountStatus(models.TextChoices):
    PENDING_ACTIVATION = "PENDING_ACTIVATION", "Pending activation"
    ACTIVE = "ACTIVE", "Active"
    SUSPENDED = "SUSPENDED", "Suspended"


class GlobalRoleCode(models.TextChoices):
    SYSTEM_ADMIN = "SYSTEM_ADMIN", "System administrator"
    TEACHER = "TEACHER", "Teacher"
    STUDENT = "STUDENT", "Student"


class SessionRevocationReason(models.TextChoices):
    LOGOUT = "LOGOUT", "Logout"
    LOGOUT_ALL = "LOGOUT_ALL", "Logout all sessions"
    ROTATED = "ROTATED", "Refresh token rotated"
    REPLAY_ATTACK = "REPLAY_ATTACK", "Refresh token replay detected"
    ADMIN_REVOKED = "ADMIN_REVOKED", "Revoked by administrator"
    PASSWORD_CHANGED = "PASSWORD_CHANGED", "Password changed"


class User(AbstractBaseUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(max_length=255)
    username = models.CharField(max_length=100)
    password = models.CharField(max_length=255, db_column="password_hash")
    last_login = models.DateTimeField(null=True, blank=True, db_column="last_login_at")
    student_id = models.CharField(max_length=50, null=True, blank=True)
    account_status = models.CharField(
        max_length=20,
        choices=AccountStatus.choices,
        default=AccountStatus.ACTIVE,
    )
    last_login_ip = models.CharField(max_length=45, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]
    objects = UserManager()

    class Meta:
        db_table = "users"
        constraints = [
            models.UniqueConstraint(fields=("email",), name="uq_users_email"),
            models.UniqueConstraint(fields=("username",), name="uq_users_username"),
            models.UniqueConstraint(
                fields=("student_id",),
                condition=Q(student_id__isnull=False),
                name="uq_users_student_id",
            ),
            models.CheckConstraint(
                condition=Q(account_status__in=AccountStatus.values),
                name="chk_user_status",
            ),
            models.CheckConstraint(
                condition=Q(email=Lower(Trim(F("email")))) & ~Q(email=""),
                name="chk_user_email_normalized",
            ),
            models.CheckConstraint(
                condition=Q(username=Lower(Trim(F("username")))) & ~Q(username=""),
                name="chk_user_username_normalized",
            ),
            models.CheckConstraint(
                condition=(
                    Q(student_id__isnull=True)
                    | (Q(student_id=Upper(Trim(F("student_id")))) & ~Q(student_id=""))
                ),
                name="chk_user_student_id_normalized",
            ),
        ]
        indexes = [
            models.Index(
                fields=("account_status",),
                condition=Q(deleted_at__isnull=True),
                name="idx_users_account_status",
            ),
        ]

    @property
    def is_active(self) -> bool:
        return self.account_status == AccountStatus.ACTIVE and self.deleted_at is None

    @property
    def is_email_verified(self) -> bool:
        """Expose allauth's current-email state, using prefetched rows when available."""
        return any(
            address.verified and address.email.casefold() == self.email.casefold()
            for address in self.emailaddress_set.all()
        )

    def __str__(self) -> str:
        return self.email


class UserProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        db_column="user_id",
        on_delete=models.CASCADE,
        related_name="profile",
    )
    first_name = models.CharField(max_length=100, default="")
    last_name = models.CharField(max_length=100, default="")
    display_name = models.CharField(max_length=200, default="", blank=True)
    avatar_url = models.CharField(max_length=500, null=True, blank=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    bio = models.TextField(null=True, blank=True)
    github_username = models.CharField(max_length=100, null=True, blank=True)
    academic_year = models.CharField(max_length=20, null=True, blank=True)
    faculty = models.CharField(max_length=100, null=True, blank=True, default="CNTT")
    timezone = models.CharField(max_length=50, default="Asia/Ho_Chi_Minh")
    preferences = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_profiles"
        indexes = [
            models.Index(
                Lower("github_username"),
                condition=Q(github_username__isnull=False),
                name="idx_profiles_github_user",
            ),
        ]


class GlobalRole(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, choices=GlobalRoleCode.choices)
    name = models.CharField(max_length=100)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "global_roles"
        constraints = [
            models.UniqueConstraint(fields=("code",), name="uq_global_roles_code"),
            models.CheckConstraint(
                condition=Q(code__in=GlobalRoleCode.values),
                name="chk_global_role_code",
            ),
        ]

    def __str__(self) -> str:
        return self.code


class UserGlobalRole(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="user_id",
        on_delete=models.CASCADE,
        related_name="global_role_assignments",
        db_index=False,
    )
    role = models.ForeignKey(
        GlobalRole,
        db_column="role_id",
        on_delete=models.RESTRICT,
        related_name="user_assignments",
        db_index=False,
    )
    assigned_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="assigned_by_user_id",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_global_roles",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_global_roles"
        constraints = [
            models.UniqueConstraint(fields=("user", "role"), name="uq_user_global_role"),
        ]
        indexes = [
            models.Index(fields=("role",), name="idx_user_global_roles_role_id"),
        ]


class UserSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="user_id",
        on_delete=models.CASCADE,
        related_name="sessions",
        db_index=False,
    )
    token_family = models.UUIDField()
    refresh_token_hash = models.CharField(max_length=64)
    refresh_jti = models.CharField(max_length=255, null=True, blank=True)
    is_revoked = models.BooleanField(default=False)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(
        max_length=100,
        choices=SessionRevocationReason.choices,
        null=True,
        blank=True,
    )
    ip_address = models.CharField(max_length=45)
    user_agent = models.TextField()
    device_name = models.CharField(max_length=100, default="Unknown Device")
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_sessions"
        constraints = [
            models.UniqueConstraint(
                fields=("refresh_token_hash",),
                name="uq_sessions_refresh_token_hash",
            ),
            models.UniqueConstraint(
                fields=("token_family",),
                condition=Q(is_revoked=False),
                name="uq_session_family_live",
            ),
            models.CheckConstraint(
                condition=Q(expires_at__gt=F("created_at")),
                name="chk_session_expiry",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        is_revoked=True,
                        revoked_at__isnull=False,
                        revoked_reason__isnull=False,
                    )
                    | Q(
                        is_revoked=False,
                        revoked_at__isnull=True,
                        revoked_reason__isnull=True,
                    )
                ),
                name="chk_session_revocation",
            ),
            models.CheckConstraint(
                condition=(
                    Q(revoked_reason__isnull=True)
                    | Q(revoked_reason__in=SessionRevocationReason.values)
                ),
                name="chk_session_revoked_reason",
            ),
        ]
        indexes = [
            models.Index(
                fields=("user", "is_revoked", "expires_at"),
                name="idx_sessions_user_active",
            ),
            models.Index(fields=("token_family",), name="idx_sessions_token_family"),
        ]


class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor_id = models.CharField(max_length=100, null=True, blank=True)
    action = models.CharField(max_length=60)
    target_user_id = models.CharField(max_length=100, null=True, blank=True)
    ip_address = models.CharField(max_length=45)
    user_agent = models.TextField()
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_logs"
        indexes = [
            models.Index(fields=("-created_at",), name="idx_audit_logs_created_at"),
            models.Index(
                fields=("target_user_id", "-created_at"),
                condition=Q(target_user_id__isnull=False),
                name="idx_audit_logs_target_user",
            ),
            models.Index(
                fields=("actor_id", "-created_at"),
                condition=Q(actor_id__isnull=False),
                name="idx_audit_logs_actor",
            ),
            models.Index(fields=("action", "-created_at"), name="idx_audit_logs_action"),
        ]


class OutboxEvent(models.Model):
    """Identity-owned durable events; a Kafka ACK is required to set published_at."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    aggregate_id = models.UUIDField()
    event_type = models.CharField(max_length=100)
    event_version = models.PositiveIntegerField(default=1)
    data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "outbox_events"
        indexes = [
            models.Index(
                fields=("created_at",),
                condition=Q(published_at__isnull=True),
                name="idx_identity_outbox_pending",
            )
        ]


class IdempotencyRecord(models.Model):
    """Durable provisioning receipt, committed with account changes, without secrets."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.CharField(max_length=100)
    endpoint_path = models.CharField(max_length=255)
    idempotency_key = models.CharField(max_length=100)
    payload_hash = models.CharField(max_length=64)
    response_status = models.PositiveSmallIntegerField()
    response_body = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "idempotency_records"
        constraints = [
            models.UniqueConstraint(
                fields=("user_id", "endpoint_path", "idempotency_key"),
                name="uq_identity_idempotency_scope",
            )
        ]
        indexes = [models.Index(fields=("created_at",), name="idx_idempotency_created_at")]
