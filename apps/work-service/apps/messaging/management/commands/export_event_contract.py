import json
from pathlib import Path

from django.core.management.base import BaseCommand
from drf_spectacular.generators import SchemaGenerator


def project_created_schema():
    project_schema = SchemaGenerator().get_schema(request=None, public=True)["components"][
        "schemas"
    ]["Project"]
    properties = {
        "event_id": {"type": "string", "format": "uuid"},
        "event_type": {"const": "project.created"},
        "event_version": {"const": 1},
        "aggregate_id": {"type": "string", "format": "uuid"},
        "occurred_at": {"type": "string", "format": "date-time"},
        "trace_id": {"type": "string", "format": "uuid"},
        "producer": {"const": "work-service"},
        "project_id": {"type": "string", "format": "uuid"},
        "entity_version": {"type": "integer", "minimum": 0},
        "project_sequence": {"type": "integer", "minimum": 1},
        "data": {"$ref": "#/$defs/Project"},
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Work project.created v1",
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(properties),
        "$defs": {"Project": project_schema},
    }


class Command(BaseCommand):
    help = "Export the actual Project create producer contract from its DRF serializer."

    def add_arguments(self, parser):
        parser.add_argument("--output", required=True)

    def handle(self, *args, **options):
        Path(options["output"]).write_text(
            json.dumps(project_created_schema(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
