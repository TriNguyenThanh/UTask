"""Only Integration verifies GitHub; Identity never calls GitHub's provider API."""

import re
from datetime import timedelta
from uuid import uuid4

import requests
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from common.errors import IdentityAPIError


class GitHubIdentityProofClient:
    """Validate the backend proof's actor/operation/provider/expiry binding."""

    @staticmethod
    def exchange_identity(user_id, code, record):
        operation = str(uuid4())
        payload = {
            "operation_id": operation,
            "user_id": str(user_id),
            "provider": "GITHUB",
            "code": code,
            "code_verifier": record["verifier"],
            "redirect_uri": record["redirect_uri"],
            "expires_at": record["expires_at"],
        }
        try:
            response = requests.post(
                settings.IDENTITY_INTEGRATION_URL.rstrip("/")
                + "/api/v1/internal/oauth/github/exchange",
                json=payload,
                headers={"X-Service-Key": settings.IDENTITY_INTEGRATION_KEY},
                timeout=5,
            )
            response.raise_for_status()
            envelope = response.json()
            proof = envelope["data"]
            expiry = parse_datetime(proof["expires_at"])
            verified_at = parse_datetime(proof["verified_at"])
            if (
                envelope.get("success") is not True
                or proof["operation_id"] != operation
                or proof["user_id"] != str(user_id)
                or proof["provider"] != "GITHUB"
                or proof["expires_at"] != record["expires_at"]
                or not expiry
                or not verified_at
                or verified_at > timezone.now() + timedelta(seconds=30)
                or verified_at < expiry - timedelta(seconds=600)
                or expiry <= timezone.now()
                or not isinstance(proof["github_user_id"], str)
                or not proof["github_user_id"].isascii()
                or not proof["github_user_id"].isdigit()
                or len(proof["github_user_id"]) > 100
                or not isinstance(proof["github_username"], str)
                or not re.fullmatch(
                    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", proof["github_username"]
                )
            ):
                raise ValueError()
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            raise IdentityAPIError(
                "OAUTH_PROVIDER_UNAVAILABLE",
                "Integration proof unavailable or invalid.",
                status_code=503,
            ) from exc
        return proof
