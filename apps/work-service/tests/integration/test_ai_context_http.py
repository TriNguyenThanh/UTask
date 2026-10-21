"""HTTP thật từ adapter AI tới Work; Identity/Classroom là fixture, không gọi LLM."""

import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.external,
    pytest.mark.django_db(transaction=True),
]


def test_existing_ai_adapter_reads_all_ten_context_pairs_over_http(
    settings, request, context_targets, actors, token, ai_keys, identity
):
    settings.STATIC_URL = "/static/"
    settings.MEDIA_URL = "/media/"
    live_server = request.getfixturevalue("live_server")
    root = Path(__file__).resolve().parents[4]
    interpreter = Path(
        os.environ.get("WORK_AI_TEST_PYTHON", root / "apps/ai-service/.venv/Scripts/python.exe")
    )
    if not interpreter.is_file():
        pytest.skip("Chưa có interpreter AI; không cài dependency trong Work test")
    payload = {
        "ai_source": str(root / "apps/ai-service/src"),
        "base": live_server.url,
        "targets": context_targets,
        "key": ai_keys["ai"],
        "user_id": str(actors["member"]),
        "token": token(actors["member"]),
    }
    runner = Path(__file__).resolve().parents[1] / "fixtures/ai_context_http_client.py"
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith(("AI_", "MOCK_TEST"))
    }
    for revoked, count in ((False, 10), (True, 3)):
        identity["active"] = not revoked
        payload["deny"] = revoked
        result = subprocess.run(
            [str(interpreter), str(runner)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=30,
            env=environment,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {"checked": count, "adapter": "InternalContextAdapter"}
