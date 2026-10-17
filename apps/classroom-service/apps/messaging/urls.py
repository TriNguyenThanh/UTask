from django.urls import path

from apps.messaging.views.activities import ClassActivityView, GroupActivityView

urlpatterns = [
    path("classes/<uuid:class_id>/activities/", ClassActivityView.as_view()),
    path("groups/<uuid:group_id>/activities/", GroupActivityView.as_view()),
]
