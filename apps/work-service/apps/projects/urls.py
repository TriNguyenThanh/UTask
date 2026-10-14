from django.urls import path

from apps.projects import views

urlpatterns = [
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
]
