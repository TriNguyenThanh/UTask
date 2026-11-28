"""Deterministic JSON encoding and hashing shared across modules."""

import hashlib
import json

from rest_framework.utils.encoders import JSONEncoder


def canonical_json(value):
    """Stable semantic JSON encoding independent of business model imports."""
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
    """Primitive JSON values safe for durable PostgreSQL JSONB persistence."""
    return json.loads(json.dumps(value, cls=JSONEncoder, ensure_ascii=False, allow_nan=False))
