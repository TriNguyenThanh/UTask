"""Domain-namespaced PostgreSQL advisory lock helpers for core_db."""

import hashlib
from enum import IntEnum

from django.db import connection


class LockNamespace(IntEnum):
    IDENTITY = 1
    CLASSROOM = 2
    WORK = 3
    MESSAGING = 4


def _key_int32(key: str) -> int:
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big", signed=True)


def advisory_xact_lock(namespace: LockNamespace | int, key: object) -> None:
    """Acquire a transaction-scoped 2-argument PostgreSQL advisory lock."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(%s, %s)",
            [int(namespace), _key_int32(str(key))],
        )


def try_advisory_lock(lock_id: int) -> bool:
    """Acquire a non-blocking session-scoped PostgreSQL advisory lock."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [int(lock_id)])
        row = cursor.fetchone()
        return bool(row and row[0])


def advisory_unlock(lock_id: int) -> None:
    """Release a session-scoped PostgreSQL advisory lock."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_unlock(%s)", [int(lock_id)])
