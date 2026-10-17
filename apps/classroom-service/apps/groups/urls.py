from django.urls import path
from apps.groups.views.groups import ClassGroupsView, GroupCodeView, GroupDetailView, GroupListView, GroupMembersView, GroupProjectsView
urlpatterns = [path('groups/', GroupListView.as_view()), path('groups/<uuid:group_id>/', GroupDetailView.as_view()), path('groups/<uuid:group_id>/members/', GroupMembersView.as_view()), path('groups/<uuid:group_id>/projects/', GroupProjectsView.as_view()), path('groups/<uuid:group_id>/invite-code/', GroupCodeView.as_view()), path('classes/<uuid:class_id>/groups/', ClassGroupsView.as_view())]
