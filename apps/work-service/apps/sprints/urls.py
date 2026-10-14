from django.urls import path

from apps.sprints import views

urlpatterns = [
    path("projects/<uuid:project_id>/sprints/", views.SprintListCreateView.as_view()),
    path("sprints/<uuid:sprint_id>/", views.SprintDetailView.as_view()),
    path(
        "projects/<uuid:project_id>/sprints/<uuid:sprint_id>/start/",
        views.SprintStartView.as_view(),
    ),
    path("sprints/<uuid:sprint_id>/tasks/", views.SprintScopeView.as_view()),
]
