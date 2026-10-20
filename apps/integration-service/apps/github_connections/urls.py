from django.urls import path

from .api import (
    AbortConnectionView,
    ConfirmConnectionView,
    ConnectionOperationView,
    GitHubContextView,
    PrepareConnectionView,
    VerifyReferenceView,
)

urlpatterns = [
    path("connection/prepare", PrepareConnectionView.as_view()),
    path("connection/confirm", ConfirmConnectionView.as_view()),
    path("connection/abort", AbortConnectionView.as_view()),
    path("connection/operations/<str:operation_id>", ConnectionOperationView.as_view()),
    path("references/verify", VerifyReferenceView.as_view()),
    path("context", GitHubContextView.as_view()),
]
