from django.urls import path
from authentication.views.auth import LoginView, healthz, jwks
urlpatterns = [path('healthz', healthz, name='healthz'), path('api/v1/auth/.well-known/jwks.json', jwks, name='identity-jwks'), path('api/v1/auth/login', LoginView.as_view(), name='identity-login')]
