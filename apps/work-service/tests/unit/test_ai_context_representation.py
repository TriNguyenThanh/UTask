import pytest

from apps.projects.serializers.ai_context import ContextDocumentSerializer, ContextRepresentation
from common.errors import WorkError
from common.internal_api import InternalJSONRenderer


def test_wire_byte_limit_accepts_exact_size_and_rejects_unshrinkable_document(monkeypatch):
    import apps.projects.serializers.ai_context as serializers

    facts = {
        "domain": "team",
        "data": {"members": [], "capacity": 0, "workload": 0},
        "as_of": "2026-10-22T00:00:00Z",
        "source_version": "1",
        "status": "available",
    }
    document = ContextDocumentSerializer(facts).data
    exact_size = len(InternalJSONRenderer().render(document))
    monkeypatch.setattr(serializers, "MAX_CONTEXT_BYTES", exact_size)
    assert ContextDocumentSerializer(facts).data == document
    monkeypatch.setattr(serializers, "MAX_CONTEXT_BYTES", exact_size - 1)
    with pytest.raises(WorkError) as failure:
        _ = ContextDocumentSerializer(facts).data
    assert failure.value.status_code == 422


def test_text_limits_preserve_unicode_and_disclose_redaction_and_truncation():
    representation = ContextRepresentation()
    text = representation.text("<p>ấ" + "ộ" * 4000 + "</p>", 4000)
    assert len(text) == 4000 and text.startswith("ấ")
    assert representation.reasons
    assert "private" not in representation.text("secret=private", 4000)
