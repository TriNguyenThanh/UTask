from django.apps import AppConfig


class ProjectsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.projects"

    def ready(self):
        import apps.projects.api_documentation  # noqa: F401
        import config.api_documentation  # noqa: F401
