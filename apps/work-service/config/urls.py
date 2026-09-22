from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.projects.views import ProjectDetailView, ProjectListCreateView, ProjectMembersView
from apps.sprints.views import ProjectSprintsView
from apps.tasks.views import ProjectTasksView, TaskDetailView

from .views import healthz

urlpatterns = [
    path("healthz", healthz),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/v1/projects", ProjectListCreateView.as_view()),
    path("api/v1/projects/<uuid:project_id>", ProjectDetailView.as_view()),
    path("api/v1/projects/<uuid:project_id>/members", ProjectMembersView.as_view()),
    path("api/v1/projects/<uuid:project_id>/tasks", ProjectTasksView.as_view()),
    path("api/v1/projects/<uuid:project_id>/sprints", ProjectSprintsView.as_view()),
    path("api/v1/tasks/<uuid:task_id>", TaskDetailView.as_view()),
]
