from django.urls import path

from apps.tasks.views.tasks import TaskDetailView, TaskLifecycleView, TaskListCreateView

urlpatterns = [
    path("projects/<uuid:project_id>/tasks/", TaskListCreateView.as_view()),
    path("tasks/<uuid:task_id>/", TaskDetailView.as_view()),
    *[
        path("tasks/<uuid:task_id>/" + action + "/", TaskLifecycleView.as_view(action=action))
        for action in ["archive", "unarchive", "restore"]
    ],
]
