from uuid import uuid4

from django.utils import timezone


def identity_event(user_id, *, stamp=None):
    return {
        "event_id": str(uuid4()),
        "event_type": "identity.user.updated",
        "event_version": 1,
        "occurred_at": (stamp or timezone.now()).isoformat(),
        "producer": "identity-service",
        "aggregate_id": str(user_id),
        "trace_id": str(uuid4()),
        "data": {"user_id": str(user_id), "display_name": "Sinh viên", "avatar_url": None},
    }
