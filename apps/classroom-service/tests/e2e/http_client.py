"""Public HTTP client; failures never include credentials or response bodies."""

import time
from uuid import uuid4

import requests


def wait_until(check, description, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = check()
            if result:
                return result
        except requests.ConnectionError:
            pass
        time.sleep(0.5)
    raise AssertionError(f"Timed out: {description}")


class GatewayClient:
    def __init__(self, gateway):
        self.gateway = gateway

    def __call__(
        self,
        method,
        path,
        *,
        token=None,
        body=None,
        key=None,
        expected=200,
        wait_for_login_limit=False,
    ):
        headers = {}
        if token:
            headers["Authorization"] = "Bearer " + token
        if method.upper() in {"POST", "PATCH", "DELETE"}:
            headers["Idempotency-Key"] = key or str(uuid4())
        deadline = time.monotonic() + 75
        while True:
            response = requests.request(
                method,
                self.gateway + path,
                headers=headers,
                json=body,
                timeout=20,
                allow_redirects=False,
            )
            if not (
                wait_for_login_limit and path == "/api/auth/login" and response.status_code == 429
            ):
                break
            try:
                delay = float(response.headers["Retry-After"]) + 0.1
            except (KeyError, TypeError, ValueError):
                break
            if delay < 0 or time.monotonic() + delay > deadline:
                break
            time.sleep(delay)
        if response.status_code != expected:
            raise AssertionError(f"{method} {path}: {response.status_code}, expected {expected}")
        if response.content and "json" in response.headers.get("Content-Type", ""):
            envelope = response.json()
            if not {"success", "message", "data", "meta", "error"} <= envelope.keys():
                raise AssertionError(f"{method} {path}: invalid response envelope")
            return envelope
        return None
