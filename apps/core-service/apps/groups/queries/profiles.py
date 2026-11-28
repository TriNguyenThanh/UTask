from uuid import UUID

from apps.accounts.interface import get_users_batch
from common.errors import CoreAPIError

IDENTITY_BATCH_LIMIT = 100


def normalize_users_batch(result) -> dict[str, dict]:
    if isinstance(result, dict):
        if isinstance(result.get("users"), list):
            rows = result["users"]
        else:
            return {str(uid): dict(item) for uid, item in result.items() if isinstance(item, dict)}
    else:
        rows = result or []
    return {
        str(item["id"]): dict(item)
        for item in rows
        if isinstance(item, dict) and item.get("id") is not None
    }


def _coerce_unique_uuids(user_ids) -> list[UUID]:
    unique: list[UUID] = []
    seen: set[UUID] = set()
    for uid in user_ids:
        if uid is None:
            continue
        parsed = uid if isinstance(uid, UUID) else UUID(str(uid))
        if parsed not in seen:
            seen.add(parsed)
            unique.append(parsed)
    return unique


def fetch_user_profiles(user_ids) -> dict[str, dict]:
    unique_ids = _coerce_unique_uuids(user_ids)
    if not unique_ids:
        return {}
    profiles: dict[str, dict] = {}
    for start in range(0, len(unique_ids), IDENTITY_BATCH_LIMIT):
        chunk = unique_ids[start : start + IDENTITY_BATCH_LIMIT]
        try:
            batch = get_users_batch(chunk)
        except CoreAPIError:
            return profiles
        profiles.update(normalize_users_batch(batch))
    return profiles
