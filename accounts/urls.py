"""
Accounts app URL routing.
"""

from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    # Auth
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("auth/refresh/", views.RefreshView.as_view(), name="token_refresh"),
    path("auth/me/", views.MeView.as_view(), name="me"),
    path("auth/change-password/", views.ChangePasswordView.as_view(), name="change_password"),
    # Admin user management
    path("auth/users/", views.UserListView.as_view(), name="admin_users"),
    path("auth/users/<int:pk>/", views.UserDetailView.as_view(), name="admin_user_detail"),
    path("auth/users/<int:pk>/reset-password/", views.UserResetPasswordView.as_view(), name="admin_user_reset_pw"),
    path("auth/users/<int:pk>/unlock/", views.UserUnlockView.as_view(), name="admin_user_unlock"),
    # Role management
    path("auth/roles/", views.RoleListView.as_view(), name="admin_roles"),
    path("auth/roles/<int:pk>/", views.RoleDetailView.as_view(), name="admin_role_detail"),
    path("auth/users/<int:pk>/role/", views.UserRoleAssignmentView.as_view(), name="admin_user_role"),
]
