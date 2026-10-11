from django.urls import path

from accounts.views.avatars import AvatarConfirmView, AvatarPresignView
from config.urls import urlpatterns as default_patterns

urlpatterns = [
    path("users/me/avatar/presigned-url", AvatarPresignView.as_view()),
    path("users/me/avatar/confirm", AvatarConfirmView.as_view()),
    *default_patterns,
]
