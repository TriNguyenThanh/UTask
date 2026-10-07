from django.urls import path
from accounts.views.profiles import CurrentUserView
urlpatterns = [path('api/v1/users/me', CurrentUserView.as_view(), name='identity-current-user')]
