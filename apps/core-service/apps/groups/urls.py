from django.urls import path

from apps.groups.views.groups import (
    ClassGroupsView,
    GroupCodeView,
    GroupDetailView,
    GroupListView,
    GroupMembersView,
    GroupProjectsView,
    MyClassGroupView,
)
from apps.groups.views.join_requests import (
    GroupJoinRequestApproveView,
    GroupJoinRequestCancelView,
    GroupJoinRequestListView,
    GroupJoinRequestRejectView,
    MyClassJoinRequestsView,
)
from apps.groups.views.members import (
    GroupJoinView,
    GroupLeaveView,
    GroupMemberDetailView,
    GroupMemberMeView,
    GroupRemoveView,
    GroupTransferView,
    TeacherAdjustmentView,
)
from apps.groups.views.recruitment import ClassOpenGroupsView, ClassUnassignedStudentsView
from apps.groups.views.topics import GroupTopicReviewView, GroupTopicSubmitView, GroupTopicView

urlpatterns = [
    path("groups/", GroupListView.as_view()),
    path("groups/join/", GroupJoinView.as_view()),
    path("groups/<uuid:group_id>/", GroupDetailView.as_view()),
    path("groups/<uuid:group_id>/members/", GroupMembersView.as_view()),
    path("groups/<uuid:group_id>/members/me/", GroupMemberMeView.as_view()),
    path("groups/<uuid:group_id>/members/<uuid:user_id>/", GroupMemberDetailView.as_view()),
    path("groups/<uuid:group_id>/join-requests/", GroupJoinRequestListView.as_view()),
    path(
        "groups/<uuid:group_id>/join-requests/<uuid:request_id>/approve/",
        GroupJoinRequestApproveView.as_view(),
    ),
    path(
        "groups/<uuid:group_id>/join-requests/<uuid:request_id>/reject/",
        GroupJoinRequestRejectView.as_view(),
    ),
    path(
        "groups/<uuid:group_id>/join-requests/<uuid:request_id>/cancel/",
        GroupJoinRequestCancelView.as_view(),
    ),
    path("groups/<uuid:group_id>/topic/", GroupTopicView.as_view()),
    path("groups/<uuid:group_id>/topic/submit/", GroupTopicSubmitView.as_view()),
    path("groups/<uuid:group_id>/topic/review/", GroupTopicReviewView.as_view()),
    path("groups/<uuid:group_id>/projects/", GroupProjectsView.as_view()),
    path("groups/<uuid:group_id>/invite-code/", GroupCodeView.as_view()),
    path("groups/<uuid:group_id>/leave/", GroupLeaveView.as_view()),
    path("groups/<uuid:group_id>/remove-member/", GroupRemoveView.as_view()),
    path("groups/<uuid:group_id>/transfer-leader/", GroupTransferView.as_view()),
    path("classes/<uuid:class_id>/groups/", ClassGroupsView.as_view()),
    path("classes/<uuid:class_id>/open-groups/", ClassOpenGroupsView.as_view()),
    path("classes/<uuid:class_id>/unassigned-students/", ClassUnassignedStudentsView.as_view()),
    path("classes/<uuid:class_id>/my-group/", MyClassGroupView.as_view()),
    path("classes/<uuid:class_id>/my-join-requests/", MyClassJoinRequestsView.as_view()),
    path("classes/<uuid:class_id>/adjust-member/", TeacherAdjustmentView.as_view()),
]
