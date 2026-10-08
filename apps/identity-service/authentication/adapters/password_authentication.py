"""Django/allauth backend hook for soft-deleted accounts."""

from allauth.account.auth_backends import AuthenticationBackend


class IdentityAuthenticationBackend(AuthenticationBackend):
    """Use allauth email/username lookup while leaving status policy to Identity."""

    def user_can_authenticate(self, user):
        return user.deleted_at is None

    def _check_password(self, user, password):
        if user is not None and user.deleted_at is not None:
            # allauth performs its built-in timing mitigation when no password
            # was checked; soft-deleted credentials must not be upgraded.
            return None
        return super()._check_password(user, password)
