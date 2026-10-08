from django.urls import path

from accounts.views.avatars import AvatarConfirmView, AvatarPresignView
from config.urls import urlpatterns as default_patterns

urlpatterns = [
    path("api/v1/users/me/avatar/presigned-url", AvatarPresignView.as_view()),
    path("api/v1/users/me/avatar/confirm", AvatarConfirmView.as_view()),
    *default_patterns,
]
