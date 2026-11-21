from django.urls import path

from notifications.views import Health, Listing, MarkRead, Preferences, ReadAll, Unread

urlpatterns = [
    path("", Listing.as_view()),
    path("unread-count", Unread.as_view()),
    path("read-all", ReadAll.as_view()),
    path("<uuid:notification_id>/read", MarkRead.as_view()),
    path("preferences", Preferences.as_view()),
    path("health", Health.as_view()),
    path("healthz", Health.as_view()),
]
