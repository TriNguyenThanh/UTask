from django.urls import path

from authentication.views.oauth import GitHubLinkView, GoogleLoginView, OAuthStartView
from config.urls import urlpatterns as default_patterns

urlpatterns = [
    path(
        "test/oauth/google/start",
        OAuthStartView.as_view(authentication_classes=[]),
        {"provider": "google"},
    ),
    path("test/oauth/google", GoogleLoginView.as_view(), {"provider": "google"}),
    path("test/oauth/github/start", OAuthStartView.as_view(), {"provider": "github"}),
    path("test/oauth/github", GitHubLinkView.as_view(), {"provider": "github"}),
    *default_patterns,
]
