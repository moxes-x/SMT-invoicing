from django.urls import path

from . import team, views

urlpatterns = [
    path("csrf/", views.CsrfView.as_view(), name="auth-csrf"),
    path("signup/", views.SignupView.as_view(), name="auth-signup"),
    path("login/", views.LoginView.as_view(), name="auth-login"),
    path("logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("me/", views.MeView.as_view(), name="auth-me"),
    path("invites/<uuid:token>/", team.invite_info, name="invite-info"),
    path("invites/<uuid:token>/accept/", team.accept_invite, name="invite-accept"),
]
