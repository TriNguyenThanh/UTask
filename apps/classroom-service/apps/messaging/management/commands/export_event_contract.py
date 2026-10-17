import json
from pathlib import Path

from django.core.management.base import BaseCommand
from drf_spectacular.generators import SchemaGenerator


def group_membership_schema():
    schemas = SchemaGenerator().get_schema(request=None, public=True)["components"]["schemas"]
    definitions = {}

    def copy_schema(value):
        if isinstance(value, list):
            return [copy_schema(item) for item in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            name = value["$ref"].rsplit("/", 1)[-1]
            if name not in definitions:
                definitions[name] = {}
                definitions[name] = copy_schema(schemas[name])
            return {"$ref": "#/$defs/" + name}
        return {key: copy_schema(item) for key, item in value.items()}

    definitions["GroupSnapshot"] = copy_schema(schemas["GroupSnapshot"])
    properties = {
        "event_id": {"type": "string", "format": "uuid"},
        "event_type": {"const": "classroom.group.membership.changed"},
        "event_version": {"const": 1},
        "aggregate_id": {"type": "string", "format": "uuid"},
        "occurred_at": {"type": "string", "format": "date-time"},
        "trace_id": {"type": "string", "format": "uuid"},
        "producer": {"const": "classroom-service"},
        "class_id": {"type": "string", "format": "uuid"},
        "entity_version": {"type": "integer", "minimum": 1},
        "class_sequence": {"type": "integer", "minimum": 1},
        "data": {"$ref": "#/$defs/GroupSnapshot"},
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Classroom group membership changed v1",
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(properties),
        "$defs": definitions,
    }


class Command(BaseCommand):
    help = "Sinh hợp đồng sự kiện từ serializer ảnh chụp nhóm đang dùng."

    def add_arguments(self, parser):
        parser.add_argument("--output", required=True)

    def handle(self, *args, **options):
        Path(options["output"]).write_text(
            json.dumps(group_membership_schema(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
