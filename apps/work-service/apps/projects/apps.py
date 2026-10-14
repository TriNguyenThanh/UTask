from django.apps import AppConfig


class ProjectsConfig(AppConfig):
    name = "apps.projects"

    def ready(self):
        import config.api_documentation  # noqa: F401
