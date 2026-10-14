from django.urls import path

from apps.collaboration.views.activities import ActivityListView
from apps.collaboration.views.comments import CommentCreateView, CommentDetailView, CommentListView

urlpatterns = [
    path("comments/", CommentCreateView.as_view()),
    path("comments/<uuid:comment_id>/", CommentDetailView.as_view()),
    path("tasks/<uuid:task_id>/comments/", CommentListView.as_view()),
    path("projects/<uuid:project_id>/comments/", CommentListView.as_view()),
    path("tasks/<uuid:task_id>/activities/", ActivityListView.as_view()),
]
