from django.urls import path

from apps.courses.views.classes import (
    ClassCodeView,
    ClassDetailView,
    ClassGroupingLockView,
    ClassListView,
    ClassStateView,
    ClassTeachersView,
    ClassTeacherView,
)
from apps.courses.views.courses import CourseArchiveView, CourseListView, CourseUpdateView
from apps.courses.views.enrollments import (
    ClassJoinView,
    EnrollmentExitView,
    EnrollmentListView,
    StudentListView,
)

urlpatterns = [
    path("courses/", CourseListView.as_view()),
    path("courses/<uuid:course_id>/", CourseUpdateView.as_view()),
    path("courses/<uuid:course_id>/archive/", CourseArchiveView.as_view()),
    path("classes/", ClassListView.as_view()),
    path("classes/join/", ClassJoinView.as_view()),
    path("classes/<uuid:class_id>/", ClassDetailView.as_view()),
    path("classes/<uuid:class_id>/state/", ClassStateView.as_view()),
    path("classes/<uuid:class_id>/lock-grouping/", ClassGroupingLockView.as_view()),
    path("classes/<uuid:class_id>/join-code/", ClassCodeView.as_view()),
    path("classes/<uuid:class_id>/teachers/", ClassTeachersView.as_view()),
    path("classes/<uuid:class_id>/teachers/assign/", ClassTeacherView.as_view()),
    path("classes/<uuid:class_id>/students/", StudentListView.as_view()),
    path("classes/<uuid:class_id>/enrollments/", EnrollmentListView.as_view()),
    path(
        "classes/<uuid:class_id>/enrollments/<uuid:enrollment_id>/exit/",
        EnrollmentExitView.as_view(),
    ),
]
