from django.urls import path

from apps.tasks.views.actions import (
    BlockView,
    RelationDetailView,
    RelationView,
    SubtaskView,
    TransitionView,
    UnblockView,
)
from apps.tasks.views.ai import ActionApplyView, BacklogApplyView, OperationView, SubtaskApplyView
from apps.tasks.views.metadata import (
    EpicDetailView,
    EpicListView,
    LabelDetailView,
    LabelListView,
    TaskLabelsView,
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
    path("projects/<uuid:project_id>/labels/", LabelListView.as_view()),
    path("projects/<uuid:project_id>/labels/<uuid:subject_id>/", LabelDetailView.as_view()),
    path("projects/<uuid:project_id>/epics/", EpicListView.as_view()),
    path("projects/<uuid:project_id>/epics/<uuid:subject_id>/", EpicDetailView.as_view()),
    path("tasks/<uuid:task_id>/labels/", TaskLabelsView.as_view()),
    path("projects/<uuid:project_id>/tasks/bulk-apply-ai/", BacklogApplyView.as_view()),
    path("tasks/<uuid:parent_task_id>/subtasks/bulk-apply-ai/", SubtaskApplyView.as_view()),
    path("projects/<uuid:project_id>/ai-operations/<uuid:operation_id>/", OperationView.as_view()),
    path("projects/<uuid:project_id>/ai-actions/apply/", ActionApplyView.as_view()),
]
