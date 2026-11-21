"""Read notifications only after resolving current Work access."""

from notifications import clients
from notifications.models import Notification


def visible(user_id, unread_only=False, read_filter=None):
    items = []
    query = Notification.objects.filter(user_id=user_id, inbox__status="processed").exclude(
        inbox__envelope__has_key="redacted"
    )
    if read_filter is not None:
        query = query.filter(read=read_filter)
    if unread_only:
        query = query.filter(read=False)
    rows = list(query.select_related("inbox").order_by("-created_at", "-id"))
    # Always resolve against Work before exposing any title, body or target.
    for row, result in zip(rows, clients.resolve_many(rows, user_id), strict=True):
        if result is not None:
            items.append(
                {
                    "id": str(row.id),
                    "category": "task-pr",
                    "title": result["title"],
                    "body": result["body"],
                    "at": row.created_at.isoformat(),
                    "read": row.read,
                    "actionLabel": "Xem chi tiết" if result.get("target") else None,
                    "target": result.get("target"),
                }
            )
    return items
