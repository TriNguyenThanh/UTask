from django.core.management.base import BaseCommand, CommandError

from apps.github_jobs.models import GitHubJob
from apps.github_jobs.services import replay_job


class Command(BaseCommand):
    help = "Giao lại job GitHub FAILED bằng ID; không nhận credential từ CLI."

    def add_arguments(self, parser):
        parser.add_argument("job_id", type=int)

    def handle(self, *args, **options):
        try:
            replay_job(options["job_id"])
        except (GitHubJob.DoesNotExist, ValueError) as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write("Job đã trở lại hàng chờ.")
