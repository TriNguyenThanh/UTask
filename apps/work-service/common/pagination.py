from django.core import signing
from django.db.models import Q
from django.utils.dateparse import parse_datetime

from common.errors import WorkError
from common.serialization import payload_hash


def paginate(queryset, params, *, scope, time_field="created_at", id_field="id"):
    try:
        page_size = int(params.get("page_size", 20))
        if not 1 <= page_size <= 100:
            raise ValueError()
    except (TypeError, ValueError) as exc:
        raise WorkError(
            "VALIDATION_ERROR", "Số lượng bản ghi mỗi trang (page_size) phải từ 1 đến 100."
        ) from exc
    total_count = queryset.count()
    fingerprint = payload_hash({"scope": scope, "order": [time_field, id_field]})
    cursor = params.get("cursor")
    if cursor:
        try:
            cut = signing.loads(cursor, salt="work-list-v1", max_age=86400)
            if cut["v"] != 1 or cut["scope"] != fingerprint:
                raise ValueError()
            stamp = parse_datetime(cut["time"])
            if stamp is None:
                raise ValueError()
            queryset = queryset.filter(
                Q(**{time_field + "__lt": stamp})
                | Q(**{time_field: stamp, id_field + "__lt": cut["id"]})
            )
        except (signing.BadSignature, ValueError, TypeError, KeyError) as exc:
            raise WorkError(
                "VALIDATION_ERROR",
                "Vị trí phân trang (cursor) không hợp lệ đối với bộ lọc hiện tại.",
            ) from exc
    rows = list(queryset.order_by("-" + time_field, "-" + id_field)[: page_size + 1])
    has_next = len(rows) > page_size
    rows = rows[:page_size]
    next_cursor = None
    if has_next:
        last = rows[-1]
        next_cursor = signing.dumps(
            {
                "v": 1,
                "scope": fingerprint,
                "time": getattr(last, time_field).isoformat(),
                "id": str(getattr(last, id_field)),
            },
            salt="work-list-v1",
            compress=True,
        )
    return rows, {
        "pagination": {
            "total_count": total_count,
            "page_size": page_size,
            "next_cursor": next_cursor,
            "prev_cursor": None,
            "has_next": has_next,
        }
    }
