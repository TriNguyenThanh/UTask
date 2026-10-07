from django.urls import path
from accounts.views.administration import AdminRoleView, AdminStatusView, AdminUsersView
from accounts.views.profiles import BatchUsersView, CurrentUserView, PublicUserView
urlpatterns = [path('api/v1/users/me', CurrentUserView.as_view(), name='identity-current-user'), path('api/v1/users/batch', BatchUsersView.as_view(), name='identity-users-batch'), path('api/v1/users/<uuid:user_id>', PublicUserView.as_view(), name='identity-public-user'), path('api/v1/admin/users', AdminUsersView.as_view(), name='identity-admin-users'), path('api/v1/admin/users/<uuid:user_id>/status', AdminStatusView.as_view(), name='identity-admin-status'), path('api/v1/admin/users/<uuid:user_id>/roles', AdminRoleView.as_view(), name='identity-admin-roles')]
