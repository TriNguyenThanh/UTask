class InvalidGitHubIdentity(ValueError):
    """The internal adapter supplied an invalid verified identity."""


class GitHubIdentityInUse(ValueError):
    """Another UTask user currently holds this GitHub identity."""


class GitHubAccountSwitchRequiresUnlink(ValueError):
    """A linked user must revoke their current identity before switching."""


class StaleGitHubVerification(ValueError):
    """The verification predates the retained link or revocation."""
