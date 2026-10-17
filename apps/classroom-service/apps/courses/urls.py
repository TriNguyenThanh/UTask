from django.urls import path
from apps.courses.views.courses import CourseArchiveView, CourseListView, CourseUpdateView
urlpatterns = [path('courses/', CourseListView.as_view()), path('courses/<uuid:course_id>/', CourseUpdateView.as_view()), path('courses/<uuid:course_id>/archive/', CourseArchiveView.as_view())]
