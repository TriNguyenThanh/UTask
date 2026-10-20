"""Project connections are Integration-owned aggregates, never Work database joins."""

from uuid import UUID, uuid4

from django.db import models
from django.db.models import Q
from django.utils import timezone


class ProjectConnection(models.Model):
    project_id = models.UUIDField(primary_key=True)
    user_id = models.UUIDField(null=True, db_index=True)
    installation_id = models.CharField(max_length=100, null=True, db_index=True)
    repo_id = models.CharField(max_length=100, null=True)
    repo_owner = models.CharField(max_length=100, null=True)
    repo_name = models.CharField(max_length=255, null=True)
    default_branch = models.CharField(max_length=100, null=True)
    status = models.CharField(max_length=12, default="DISCONNECTED")
    generation = models.PositiveBigIntegerField(default=0)
    source_version = models.PositiveBigIntegerField(default=0)
    event_sequence = models.PositiveBigIntegerField(default=0)
    current_operation = models.CharField(max_length=100, default="")
    accepted_operation = models.CharField(max_length=100, default="")
    accepted_generation = models.PositiveBigIntegerField(default=0)
    credential_generation = models.PositiveBigIntegerField(default=0)
    needs_revalidation = models.BooleanField(default=False)
    revision = models.PositiveBigIntegerField(default=0)
    synced_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=~Q(project_id=UUID(int=0)), name="ck_conn_project_id"),
            models.CheckConstraint(
                condition=Q(accepted_generation__lte=models.F("generation")),
                name="ck_conn_accepted_generation",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status="DISCONNECTED")
                    | (
                        Q(repo_id__regex=r"^[1-9][0-9]{0,99}$", accepted_generation__gte=1)
                        & ~Q(accepted_operation="")
                    )
                ),
                name="ck_conn_connected_identity",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status="CONNECTED",
                        user_id__isnull=False,
                        installation_id__isnull=False,
                        repo_id__isnull=False,
                        repo_owner__isnull=False,
                        repo_name__isnull=False,
                        default_branch__isnull=False,
                        generation__gte=1,
                        source_version__gte=1,
                    )
                    | Q(
                        status="DISCONNECTED",
                        installation_id__isnull=True,
                        repo_id__isnull=True,
                        repo_owner__isnull=True,
                        repo_name__isnull=True,
                        default_branch__isnull=True,
                    )
                ),
                name="ck_project_connection_shape",
            ),
        ]


class ConnectionOperation(models.Model):
    project_id = models.UUIDField()
    operation_id = models.CharField(max_length=100)
    caller = models.CharField(max_length=8, default="work")
    user_id = models.UUIDField()
    action = models.CharField(max_length=10)
    payload_hash = models.CharField(max_length=64)
    expected_generation = models.PositiveBigIntegerField()
    generation = models.PositiveBigIntegerField()
    state = models.CharField(max_length=10, default="PREPARED")
    result = models.JSONField(default=dict)
    prepared_result = models.JSONField(default=dict)
    installation_id = models.CharField(max_length=100, null=True)
    credential_generation = models.PositiveBigIntegerField(default=0)
    expires_at = models.DateTimeField()
    retain_until = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~Q(project_id=UUID(int=0)), name="ck_conn_operation_project"
            ),
            models.CheckConstraint(
                condition=Q(operation_id__regex=r"^[A-Za-z0-9._:-]{1,100}$")
                & ~Q(operation_id__in=[".", ".."]),
                name="ck_conn_operation_id",
            ),
            models.CheckConstraint(
                condition=Q(payload_hash__regex=r"^[a-f0-9]{64}$"),
                name="ck_conn_operation_digest",
            ),
            models.UniqueConstraint(
                fields=["project_id", "operation_id"], name="uq_conn_operation"
            ),
            models.CheckConstraint(condition=Q(caller="work"), name="ck_conn_operation_caller"),
            models.CheckConstraint(
                condition=Q(action__in=["CONNECT", "DISCONNECT"]), name="ck_conn_operation_action"
            ),
            models.CheckConstraint(
                condition=Q(state__in=["PREPARED", "CONFIRMED", "ABORTED", "EXPIRED"]),
                name="ck_conn_operation_state",
            ),
            models.CheckConstraint(
                condition=Q(generation__gte=1), name="ck_conn_operation_generation"
            ),
        ]
        indexes = [
            models.Index(
                fields=["expires_at"],
                condition=Q(state="PREPARED"),
                name="ix_conn_operation_expire",
            ),
            models.Index(fields=["retain_until"], name="ix_conn_operation_retention"),
        ]


class ConnectionProviderFence(models.Model):
    """A small global fence prevents a late HTTP response crossing an installation webhook."""

    name = models.CharField(max_length=16, primary_key=True, default="github")
    revision = models.PositiveBigIntegerField(default=0)


class IntegrationOutboxEvent(models.Model):
    event_id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    project_id = models.UUIDField()
    event_sequence = models.PositiveBigIntegerField()
    envelope = models.JSONField()
    state = models.CharField(max_length=12, default="PENDING")
    attempts = models.PositiveIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now)
    lease_id = models.UUIDField(null=True)
    lease_until = models.DateTimeField(null=True)
    published_at = models.DateTimeField(null=True)
    last_error_class = models.CharField(max_length=80, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project_id", "event_sequence"], name="uq_conn_outbox_sequence"
            ),
            models.CheckConstraint(
                condition=Q(event_sequence__gte=1), name="ck_conn_outbox_sequence"
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        state="PENDING",
                        lease_id__isnull=True,
                        lease_until__isnull=True,
                        published_at__isnull=True,
                    )
                    | Q(
                        state="PUBLISHING",
                        lease_id__isnull=False,
                        lease_until__isnull=False,
                        published_at__isnull=True,
                    )
                    | Q(
                        state="PUBLISHED",
                        lease_id__isnull=True,
                        lease_until__isnull=True,
                        published_at__isnull=False,
                    )
                ),
                name="ck_conn_outbox_state",
            ),
        ]
        indexes = [
            models.Index(
                fields=["available_at"],
                condition=~Q(state="PUBLISHED"),
                name="ix_conn_outbox_pending",
            ),
        ]
