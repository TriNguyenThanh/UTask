from django.urls import path

from apps.projects import views
from apps.projects.views.ai_context import AIAuthorizeView, AIContextView
from apps.projects.views.board import BoardColumnView, BoardView
from apps.projects.views.dashboard import DashboardView
from apps.projects.views.states import StateDetailView

urlpatterns = [
    path(
        "api/v1/internal/ai/targets/<str:target_type>/<str:target_id>/authorize",
        AIAuthorizeView.as_view(),
        name="ai-target-authorize",
    ),
    path(
        "api/v1/internal/ai/targets/<str:target_type>/<str:target_id>/contexts/<str:domain>",
        AIContextView.as_view(),
        name="ai-target-context",
    ),
    path("projects/", views.ProjectListCreateView.as_view(), name="project-list"),
    path("projects/<uuid:project_id>/", views.ProjectDetailView.as_view(), name="project-detail"),
    path(
        "projects/<uuid:project_id>/archive/",
        views.ProjectArchiveView.as_view(),
        name="project-archive",
    ),
    path(
        "projects/<uuid:project_id>/unarchive/",
        views.ProjectArchiveView.as_view(archive=False),
        name="project-unarchive",
    ),
    path(
        "projects/<uuid:project_id>/members/",
        views.ProjectMemberListView.as_view(),
        name="project-members",
    ),
    path(
        "projects/<uuid:project_id>/members/<uuid:user_id>/capacity/",
        views.CapacityView.as_view(),
        name="member-capacity",
    ),
    path("projects/<uuid:project_id>/states/", views.StateListView.as_view(), name="state-list"),
    path(
        "projects/<uuid:project_id>/states/<uuid:state_id>/",
        StateDetailView.as_view(),
        name="state-detail",
    ),
    path("projects/<uuid:project_id>/kanban/", BoardView.as_view(), name="project-board"),
    path(
        "projects/<uuid:project_id>/kanban/states/<uuid:state_id>/tasks/",
        BoardColumnView.as_view(),
        name="board-column",
    ),
    path(
        "projects/<uuid:project_id>/dashboard/", DashboardView.as_view(), name="project-dashboard"
    ),
]
