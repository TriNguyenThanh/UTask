from notifications.configuration import validate_production

from .base import *  # noqa: F403

validate_production(globals())
