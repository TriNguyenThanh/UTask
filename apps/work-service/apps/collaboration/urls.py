from django.urls import path

from apps.collaboration.views.activities import ActivityListView
from apps.collaboration.views.attachments import (
    AttachmentDeleteView,
    AttachmentDownloadView,
    AttachmentListConfirmView,
    PresignView,
)
from apps.collaboration.views.comments import CommentCreateView, CommentDetailView, CommentListView

urlpatterns = [
    path("comments/", CommentCreateView.as_view()),
    path("comments/<uuid:comment_id>/", CommentDetailView.as_view()),
    path("tasks/<uuid:task_id>/comments/", CommentListView.as_view()),
    path("projects/<uuid:project_id>/comments/", CommentListView.as_view()),
    path("tasks/<uuid:task_id>/activities/", ActivityListView.as_view()),
]
for prefix in ["tasks/<uuid:task_id>/", "projects/<uuid:project_id>/"]:
    urlpatterns += [
        path(prefix + "attachments/presigned-url/", PresignView.as_view()),
        path(prefix + "attachments/", AttachmentListConfirmView.as_view()),
        path(
            prefix + "attachments/<uuid:attachment_id>/download/", AttachmentDownloadView.as_view()
        ),
        path(prefix + "attachments/<uuid:attachment_id>/", AttachmentDeleteView.as_view()),
    ]
