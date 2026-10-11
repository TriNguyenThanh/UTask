import importlib

import pytest
from django.core.management import call_command
from django.urls import clear_url_caches

pytestmark = pytest.mark.contract


def test_openapi_with_enabled_flags_reads_real_urlconf(settings, tmp_path):
    import json

    urls = [
        importlib.import_module(name)
        for name in ("authentication.urls", "accounts.urls", "config.urls")
    ]
    settings.IDENTITY_GOOGLE_ENABLED = True
    settings.IDENTITY_GITHUB_ENABLED = True
    settings.IDENTITY_AVATAR_ENABLED = True
    try:
        for module in urls:
            importlib.reload(module)
        clear_url_caches()
        target = tmp_path / "schema.json"
        call_command("export_identity_api", output=str(target))
        schema = json.loads(target.read_text())
        assert sum(len(methods) for methods in schema["paths"].values()) == 33
        assert schema["paths"]["/oauth/google"].keys() == {"post", "delete"}
        assert schema["paths"]["/oauth/github"].keys() == {"post", "delete"}
        assert schema["paths"]["/users/me/avatar/confirm"].keys() == {"post"}
        for route in ("/oauth/google", "/oauth/google/start"):
            assert not any(
                "jwtAuth" in item for item in schema["paths"][route]["post"].get("security", [])
            )
        for route, method in (
            ("/oauth/google", "delete"),
            ("/oauth/github/start", "post"),
        ):
            assert {"jwtAuth": []} in schema["paths"][route][method]["security"]
    finally:
        settings.IDENTITY_GOOGLE_ENABLED = False
        settings.IDENTITY_GITHUB_ENABLED = False
        settings.IDENTITY_AVATAR_ENABLED = False
        for module in urls:
            importlib.reload(module)
        clear_url_caches()
