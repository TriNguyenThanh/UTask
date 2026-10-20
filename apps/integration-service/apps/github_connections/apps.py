from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class GitHubConnectionsConfig(AppConfig):
    name = "apps.github_connections"

    def ready(self):
        if not settings.INTEGRATION_CONNECTIONS_ENABLED:
            if settings.INTEGRATION_AI_CONTEXT_ENABLED:
                raise ImproperlyConfigured("AI context requires Integration connections")
            return
        from common.internal_auth import service_keys

        keys = service_keys()
        outbound = settings.INTEGRATION_WORK_SERVICE_KEY
        if (
            not settings.INTEGRATION_GITHUB_APP_ENABLED
            or not keys
            or "work" not in keys
            or settings.INTEGRATION_AI_CONTEXT_ENABLED
            and "ai" not in keys
            or not isinstance(outbound, str)
            or not outbound.isascii()
            or not outbound.isprintable()
            or outbound.strip() != outbound
            or not 32 <= len(outbound) <= 4096
            or any(outbound.encode() in values for values in keys.values())
        ):
            raise ImproperlyConfigured("Integration connection configuration is invalid")
