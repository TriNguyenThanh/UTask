from django.urls import path

from apps.integrations import views
from apps.integrations.views.accounts import UsernameView, VerificationRequestView

urlpatterns = [
    path("projects/<uuid:project_id>/github/repository/", views.RepositoryView.as_view()),
    path("tasks/<uuid:task_id>/github-links/", views.LinkListCreateView.as_view()),
    path(
        "tasks/<uuid:task_id>/github-links/<uuid:link_id>/confirm/", views.LinkConfirmView.as_view()
    ),
    path("tasks/<uuid:task_id>/github-links/<uuid:link_id>/", views.LinkDetailView.as_view()),
    path("projects/<uuid:project_id>/members/<uuid:user_id>/github/", UsernameView.as_view()),
    path(
        "projects/<uuid:project_id>/members/<uuid:user_id>/github/request-verification/",
        VerificationRequestView.as_view(),
    ),
]
