"""Export the three per-domain OpenAPI contracts from Core Service without breaking teams."""

from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from drf_spectacular.settings import patched_settings

DOMAIN_CONTRACTS = {
    "identity": {
        "urlconf": "config.urls_domains.identity",
        "filename": "identity-service.yaml",
        "title": "UTask Identity API",
        "version": "1.8",
    },
    "classroom": {
        "urlconf": "config.urls_domains.classroom",
        "filename": "classroom-service.yaml",
        "title": "UTask Classroom API",
        "version": "1.4",
    },
    "work": {
        "urlconf": "config.urls_domains.work",
        "filename": "work-service.yaml",
        "title": "UTask Work API",
        "version": "1.5",
    },
}


class Command(BaseCommand):
    help = "Export identity-service.yaml, classroom-service.yaml, and/or work-service.yaml."

    def add_arguments(self, parser):
        parser.add_argument(
            "--domain",
            choices=[*DOMAIN_CONTRACTS.keys(), "all"],
            default="all",
            help="Which domain OpenAPI contract to export (default: all).",
        )
        parser.add_argument(
            "--output-dir",
            default=str(Path(settings.BASE_DIR).parent.parent / "contracts" / "api"),
            help="Directory to write YAML contracts into.",
        )
        parser.add_argument(
            "--validate",
            action="store_true",
            help="Validate each generated schema via drf-spectacular.",
        )

    def handle(self, *args, **options):
        output_dir = Path(options["output_dir"])
        if not output_dir.exists():
            raise CommandError(f"Output directory does not exist: {output_dir}")
        domains = (
            list(DOMAIN_CONTRACTS.keys()) if options["domain"] == "all" else [options["domain"]]
        )
        for domain in domains:
            spec = DOMAIN_CONTRACTS[domain]
            target = output_dir / spec["filename"]
            with patched_settings({"TITLE": spec["title"], "VERSION": spec["version"]}):
                call_command(
                    "spectacular",
                    urlconf=spec["urlconf"],
                    file=str(target),
                    validate=options["validate"],
                    fail_on_warn=False,
                )
            self.stdout.write(self.style.SUCCESS(f"Exported {domain} contract -> {target}"))
