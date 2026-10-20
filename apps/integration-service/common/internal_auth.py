"""Caller identity for the private Work and AI boundary."""

import json
from secrets import compare_digest

from django.conf import settings
from rest_framework.permissions import BasePermission


def service_keys():
    """Return validated keys; an invalid entry closes the entire boundary."""
    configured = getattr(settings, "INTEGRATION_SERVICE_KEYS", {})
    try:
        if isinstance(configured, str):
            configured = json.loads(configured)
        if not isinstance(configured, dict) or not configured:
            return None
        result = {}
        seen = set()
        for caller, values in configured.items():
            if caller not in {"work", "ai"}:
                return None
            values = [values] if isinstance(values, str) else values
            if not isinstance(values, list) or not 1 <= len(values) <= 2:
                return None
            result[caller] = []
            for value in values:
                if not isinstance(value, str) or not value.isascii() or not value.isprintable():
                    return None
                key = value.encode("ascii")
                if len(key) < 32 or len(key) > 4096 or value.strip() != value or key in seen:
                    return None
                seen.add(key)
                result[caller].append(key)
        return result
    except (ValueError, TypeError, UnicodeError):
        return None


class InternalServicePermission(BasePermission):
    message = "Caller nội bộ không được phép."
    code = "INTERNAL_SERVICE_DENIED"

    def has_permission(self, request, view):
        request.integration_caller = None
        allowed = getattr(view, "allowed_callers", ())
        keys = service_keys()
        presented = request.headers.get("X-Service-Key", "")
        if (
            not keys
            or not isinstance(allowed, tuple)
            or not allowed
            or any(caller not in {"work", "ai"} for caller in allowed)
            or not isinstance(presented, str)
            or not presented.isascii()
            or not 32 <= len(presented) <= 4096
        ):
            return False
        matched = None
        for caller, values in keys.items():
            for key in values:
                if compare_digest(presented.encode("ascii"), key):
                    matched = caller
        if matched not in allowed:
            return False
        request.integration_caller = matched
        return True
