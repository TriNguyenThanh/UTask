from apps.courses.permissions import bearer
from common.errors import ClassroomError
from infrastructure.identity import IdentityClient

IDENTITY_BATCH_LIMIT = 100


def fetch_user_profiles(request, user_ids):
    unique_ids = list(dict.fromkeys(str(uid) for uid in user_ids if uid is not None))
    if not unique_ids:
        return {}
    token = bearer(request)
    client = IdentityClient()
    profiles = {}
    for start in range(0, len(unique_ids), IDENTITY_BATCH_LIMIT):
        chunk = unique_ids[start : start + IDENTITY_BATCH_LIMIT]
        try:
            rows = client.users(token, chunk)
        except ClassroomError:
            return profiles
        for item in rows:
            profiles[str(item["id"])] = item
    return profiles
