"""
Accounts app views — login / logout / me / change-password / admin user management.
"""
from django.contrib.auth.models import User
from django.db import models
from rest_framework import generics, permissions, status, views
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import LoginAttempt, UserRole, UserProfile, PERMISSION_GROUPS
from .permissions import HasPermission, get_user_permissions
from .serializers import (
    AdminCreateUserSerializer,
    AdminResetPasswordSerializer,
    AdminUserListSerializer,
    ChangePasswordSerializer,
    LoginSerializer,
    RoleSerializer,
    RoleUpdateSerializer,
    UserRoleAssignmentSerializer,
    UserSerializer,
)
from .utils import get_client_ip, get_client_ip_info


# ═══════════════════════════════════════════════════════════════════
# Permissions
# ═══════════════════════════════════════════════════════════════════

class IsSuperUser(permissions.BasePermission):
    """仅超级管理员可访问。"""

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_superuser


# ═══════════════════════════════════════════════════════════════════
# Auth endpoints
# ═══════════════════════════════════════════════════════════════════

class LoginView(views.APIView):
    """POST /api/auth/login/ — returns JWT access + refresh tokens (IP-bound)."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        client_ip = get_client_ip(request)

        # ── Create IP-bound tokens ──────────────────────────
        refresh = RefreshToken.for_user(user)
        refresh["ip"] = client_ip
        # access token inherits claims from refresh (including "ip")

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "is_superuser": user.is_superuser,
                    "permissions": sorted(get_user_permissions(user)),
                },
                "ips": get_client_ip_info(request),
            }
        )


class RefreshView(views.APIView):
    """POST /api/auth/refresh/ — IP-bound refresh → new access token.

    Validates that the refresh token's embedded IP matches the request IP
    before issuing a new access token.  Delegates the actual token rotation
    logic to SimpleJWT's TokenRefreshSerializer.
    """

    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        from rest_framework_simplejwt.settings import api_settings

        refresh_token_str = request.data.get("refresh")
        if not refresh_token_str:
            return Response(
                {"detail": "缺少 refresh 参数。"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh_token_str)
        except Exception:
            return Response(
                {"detail": "refresh token 无效或已过期。"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # ── IP binding check ────────────────────────────────
        token_ip = token.get("ip")
        if token_ip is not None:
            request_ip = get_client_ip(request)
            if request_ip != token_ip:
                return Response(
                    {
                        "detail": (
                            f"Token IP 绑定验证失败：token 签发 IP ({token_ip}) "
                            f"与请求 IP ({request_ip}) 不匹配。"
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        # ── Rotate tokens (delegate to SimpleJWT) ────────────
        data = {"access": str(token.access_token)}

        if api_settings.ROTATE_REFRESH_TOKENS:
            if api_settings.BLACKLIST_AFTER_ROTATION:
                try:
                    token.blacklist()
                except AttributeError:
                    pass
            token.set_jti()
            token.set_exp()
            token.set_iat()
            data["refresh"] = str(token)

        return Response(data)


class LogoutView(views.APIView):
    """POST /api/auth/logout/ — blacklist the refresh token (client discards access token)."""

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                pass  # token already expired / invalid — still a successful logout
        return Response({"detail": "已退出登录。"})


class MeView(generics.RetrieveAPIView):
    """GET /api/auth/me/ — return current user profile."""

    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class ChangePasswordView(views.APIView):
    """POST /api/auth/change-password/"""

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save()
        return Response({"detail": "密码修改成功。"})


# ═══════════════════════════════════════════════════════════════════
# Admin — user management (superuser only)
# ═══════════════════════════════════════════════════════════════════

class UserListView(views.APIView):
    """GET /api/auth/users/ — 列出所有用户。POST /api/auth/users/ — 创建新用户。"""

    permission_classes = [permissions.IsAuthenticated, HasPermission]
    permission_map = {"GET": "system:view", "POST": "system:users"}

    def get(self, request):
        users = User.objects.all().order_by("-date_joined")
        serializer = AdminUserListSerializer(users, many=True)
        return Response({"users": serializer.data, "total": len(serializer.data)})

    def post(self, request):
        serializer = AdminCreateUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        user = User.objects.create_user(
            username=data["username"],
            email=data.get("email", ""),
            password=data["password"],
        )
        user.is_superuser = data.get("is_superuser", False)
        user.is_staff = data.get("is_superuser", False)
        user.save()

        return Response(
            {
                "status": "ok",
                "user": AdminUserListSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class UserDetailView(views.APIView):
    """DELETE /api/auth/users/<id>/ — 删除用户（或禁用）。"""

    permission_classes = [permissions.IsAuthenticated, HasPermission]
    required_permission = "system:users"

    def delete(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"error": "用户不存在"}, status=404)

        if user.id == request.user.id:
            return Response({"error": "不能删除自己"}, status=400)

        action = request.query_params.get("action", "delete")
        if action == "deactivate":
            user.is_active = False
            user.save(update_fields=["is_active"])
            return Response({"status": "ok", "is_active": False})

        user.delete()
        return Response({"status": "ok"})


class UserResetPasswordView(views.APIView):
    """PUT /api/auth/users/<id>/reset-password/ — 管理员强制重置用户密码。"""

    permission_classes = [permissions.IsAuthenticated, HasPermission]
    required_permission = "system:users"

    def put(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"error": "用户不存在"}, status=404)

        serializer = AdminResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user.set_password(serializer.validated_data["new_password"])
        user.save()

        return Response({"status": "ok", "detail": f"用户 {user.username} 的密码已重置。"})


class UserUnlockView(views.APIView):
    """POST /api/auth/users/<id>/unlock/ — 清除用户的所有登录失败记录。"""

    permission_classes = [permissions.IsAuthenticated, HasPermission]
    required_permission = "system:users"

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"error": "用户不存在"}, status=404)

        deleted, _ = LoginAttempt.objects.filter(
            username=user.username, success=False,
        ).delete()

        return Response({
            "status": "ok",
            "detail": f"已清除 {user.username} 的 {deleted} 条登录失败记录。",
            "cleared": deleted,
        })


# ═══════════════════════════════════════════════════════════════════
# Role management (system:users permission required)
# ═══════════════════════════════════════════════════════════════════

class RoleListView(views.APIView):
    """GET /api/auth/roles/ — 列出所有角色。
    POST /api/auth/roles/ — 创建自定义角色。"""

    permission_classes = [permissions.IsAuthenticated, HasPermission]
    permission_map = {"GET": "system:view", "POST": "system:users"}

    def get(self, request):
        roles = UserRole.objects.annotate(
            user_count=models.Count("users")
        ).order_by("-is_builtin", "name")

        data = []
        for r in roles:
            data.append({
                "id": r.id,
                "name": r.name,
                "display_name": r.display_name,
                "description": r.description,
                "permissions": r.permissions,
                "is_builtin": r.is_builtin,
                "user_count": r.user_count,
            })
        return Response({"roles": data})

    def post(self, request):
        name = (request.data.get("name") or "").strip()
        display_name = (request.data.get("display_name") or "").strip()
        description = request.data.get("description", "")
        permissions_list = request.data.get("permissions", [])

        if not name:
            return Response({"error": "角色标识不能为空"}, status=400)
        if not display_name:
            return Response({"error": "显示名称不能为空"}, status=400)
        if UserRole.objects.filter(name=name).exists():
            return Response({"error": f"角色标识 '{name}' 已存在"}, status=400)

        role = UserRole.objects.create(
            name=name,
            display_name=display_name,
            description=description,
            permissions=permissions_list,
            is_builtin=False,
        )
        return Response({
            "status": "ok",
            "role": {
                "id": role.id,
                "name": role.name,
                "display_name": role.display_name,
                "description": role.description,
                "permissions": role.permissions,
                "is_builtin": role.is_builtin,
                "user_count": 0,
            },
        }, status=status.HTTP_201_CREATED)


class RoleDetailView(views.APIView):
    """PUT /api/auth/roles/<id>/ — 更新角色。
    DELETE /api/auth/roles/<id>/ — 删除角色（仅非内置）。"""

    permission_classes = [permissions.IsAuthenticated, HasPermission]
    required_permission = "system:users"

    def put(self, request, pk):
        try:
            role = UserRole.objects.get(pk=pk)
        except UserRole.DoesNotExist:
            return Response({"error": "角色不存在"}, status=404)

        display_name = request.data.get("display_name")
        description = request.data.get("description")
        permissions_list = request.data.get("permissions")

        if display_name is not None:
            role.display_name = display_name
        if description is not None:
            role.description = description
        if permissions_list is not None:
            role.permissions = permissions_list

        role.save()

        return Response({
            "status": "ok",
            "role": {
                "id": role.id,
                "name": role.name,
                "display_name": role.display_name,
                "description": role.description,
                "permissions": role.permissions,
                "is_builtin": role.is_builtin,
            },
        })

    def delete(self, request, pk):
        try:
            role = UserRole.objects.get(pk=pk)
        except UserRole.DoesNotExist:
            return Response({"error": "角色不存在"}, status=404)

        if role.is_builtin:
            return Response({"error": "内置角色不可删除"}, status=400)

        role.delete()
        return Response({"status": "ok", "detail": f"角色 '{role.display_name}' 已删除。"})


class PermissionsMetaView(views.APIView):
    """GET /api/auth/permissions/ — 权限码分组元数据（供前端渲染权限复选框）。"""

    permission_classes = [permissions.IsAuthenticated, HasPermission]
    required_permission = "system:view"

    def get(self, request):
        return Response({"groups": PERMISSION_GROUPS})


class UserRoleAssignmentView(views.APIView):
    """PUT /api/auth/users/<id>/role/ — 为用户分配角色。"""

    permission_classes = [permissions.IsAuthenticated, HasPermission]
    required_permission = "system:users"

    def put(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"error": "用户不存在"}, status=404)

        serializer = UserRoleAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role_id = serializer.validated_data["role_id"]

        try:
            role = UserRole.objects.get(pk=role_id)
        except UserRole.DoesNotExist:
            return Response({"error": "角色不存在"}, status=404)

        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.role = role
        profile.save(update_fields=["role"])

        return Response({
            "status": "ok",
            "user_id": user.id,
            "username": user.username,
            "role_id": role.id,
            "role_name": role.display_name,
        })

    def delete(self, request, pk):
        """移除用户角色（回到无权限状态）。"""
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"error": "用户不存在"}, status=404)

        profile = getattr(user, "profile", None)
        if profile:
            profile.role = None
            profile.save(update_fields=["role"])

        return Response({
            "status": "ok",
            "detail": f"已移除 {user.username} 的角色。",
        })
