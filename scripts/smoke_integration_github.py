"""Read-only external M4 smoke; credentials come from environment, never CLI/logs."""

import json
import os
import re
import urllib.request
from types import SimpleNamespace
from urllib.parse import urlsplit


class SmokeFailure(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def read_response(url, *, headers, timeout, allow_redirects):
    if allow_redirects:
        raise ValueError("Redirects are disabled for authenticated smoke")
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(
        urllib.request.Request(url, headers=headers), timeout=timeout[1]
    ) as response:
        raw = response.read(1_048_577)
        if len(raw) > 1_048_576:
            raise ValueError("Response too large")
        payload = json.loads(raw)
        return SimpleNamespace(status_code=response.status, json=lambda: payload)


def smoke(*, base_url, bearer, installation_id=None, request=read_response):
    try:
        parsed = urlsplit(base_url)
        valid = (
            parsed.scheme == "https"
            or parsed.scheme == "http"
            and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        )
        if (
            not valid
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError()
        if not isinstance(bearer, str) or not re.fullmatch(r"[A-Za-z0-9._~-]+", bearer):
            raise ValueError()
        if installation_id is not None and not re.fullmatch(
            r"[1-9][0-9]{0,99}", installation_id
        ):
            raise ValueError()
    except (ValueError, TypeError):
        raise SmokeFailure("Cấu hình smoke không hợp lệ.") from None

    def get(path):
        try:
            response = request(
                base_url.rstrip("/") + path,
                headers={"Authorization": f"Bearer {bearer}"},
                timeout=(2, 5),
                allow_redirects=False,
            )
            if response.status_code != 200:
                raise ValueError()
            result = response.json()
            if (
                not isinstance(result, dict)
                or result.get("success") is not True
                or not isinstance(result.get("data"), dict)
            ):
                raise ValueError()
            return result["data"]
        except (OSError, ValueError, TypeError):
            raise SmokeFailure(
                "Smoke HTTP không đạt; kiểm tra cấu hình và quyền, không in response chứa dữ liệu cá nhân."
            ) from None

    account = get("/api/v1/github/account")
    if (
        account.get("status") != "LINKED"
        or account.get("authorization_status") != "ACTIVE"
    ):
        raise SmokeFailure("Actor cần hoàn tất consent GitHub App trước smoke.")
    installations = get("/api/v1/github/installations")
    if not isinstance(installations.get("items"), list):
        raise SmokeFailure("Danh sách installation không hợp lệ.")
    repositories = None
    if installation_id:
        repositories = get(
            f"/api/v1/github/installations/{installation_id}/repositories"
        )
        if not isinstance(repositories.get("items"), list):
            raise SmokeFailure("Danh sách repository không hợp lệ.")
    return {
        "installations_on_page": len(installations["items"]),
        "repositories_on_page": len(repositories["items"])
        if repositories is not None
        else None,
    }


def main():
    try:
        result = smoke(
            base_url=os.environ.get("INTEGRATION_SMOKE_URL", ""),
            bearer=os.environ.get("INTEGRATION_SMOKE_BEARER", ""),
            installation_id=os.environ.get("INTEGRATION_SMOKE_INSTALLATION_ID") or None,
        )
    except SmokeFailure as exc:
        print(str(exc))
        return 1
    print(f"M4 read-only smoke đạt: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
