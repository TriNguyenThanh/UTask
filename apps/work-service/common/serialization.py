import hashlib
import json

from rest_framework.utils.encoders import JSONEncoder


def canonical_json(value):
    """Stable semantic hash encoding, independent of business model imports."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        allow_nan=False,
    )


def payload_hash(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def json_value(value):
    """The same primitive JSON values that DRF renders, safe for durable JSONB."""
    return json.loads(json.dumps(value, cls=JSONEncoder, ensure_ascii=False, allow_nan=False))
