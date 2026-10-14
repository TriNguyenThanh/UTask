from django.urls import path

from apps.tasks.views.actions import (
    BlockView,
    RelationDetailView,
    RelationView,
    SubtaskView,
    TransitionView,
    UnblockView,
)
from apps.tasks.views.tasks import TaskDetailView, TaskLifecycleView, TaskListCreateView

urlpatterns = [
    path("projects/<uuid:project_id>/tasks/", TaskListCreateView.as_view()),
    path("tasks/<uuid:task_id>/", TaskDetailView.as_view()),
    *[
        path("tasks/<uuid:task_id>/" + action + "/", TaskLifecycleView.as_view(action=action))
        for action in ["archive", "unarchive", "restore"]
    ],
    path("tasks/<uuid:parent_task_id>/subtasks/", SubtaskView.as_view()),
    path("tasks/<uuid:task_id>/transition/", TransitionView.as_view()),
    path("tasks/<uuid:task_id>/block/", BlockView.as_view()),
    path("tasks/<uuid:task_id>/unblock/", UnblockView.as_view()),
    path("tasks/<uuid:task_id>/relations/", RelationView.as_view()),
    path("tasks/<uuid:task_id>/relations/<uuid:relation_id>/", RelationDetailView.as_view()),
]
