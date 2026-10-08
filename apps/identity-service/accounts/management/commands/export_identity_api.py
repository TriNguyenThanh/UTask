"""Export and validate the actual Identity URL/serializer contract."""

from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Export and validate OpenAPI for routes enabled in the current environment."

    def add_arguments(self, parser):
        parser.add_argument("--output", required=True)

    def handle(self, *args, **options):
        from drf_spectacular.generators import SchemaGenerator
        from drf_spectacular.renderers import OpenApiJsonRenderer
        from drf_spectacular.validation import validate_schema

        schema = SchemaGenerator(urlconf="config.urls").get_schema(public=True)
        validate_schema(schema)
        target = Path(options["output"]).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(OpenApiJsonRenderer().render(schema))
        count = sum(len(path) for path in schema["paths"].values())
        self.stdout.write(self.style.SUCCESS(f"Validated Identity OpenAPI: {count} operations."))
