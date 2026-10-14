from django.apps import AppConfig


class TasksConfig(AppConfig):
    name = "apps.tasks"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from apps.tasks import api_documentation  # noqa: F401
