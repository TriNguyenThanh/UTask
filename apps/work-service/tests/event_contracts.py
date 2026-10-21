"""Validate persisted producer envelopes against the canonical repository contract."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


def assert_event_contract(event):
    path = Path(__file__).resolve().parents[3] / "contracts" / "events"
    schema = json.loads((path / f"{event.event_type}.v1.json").read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(event.data)
