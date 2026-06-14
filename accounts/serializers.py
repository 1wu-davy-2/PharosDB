"""
Accounts app serializers — user auth & profile.
"""
from datetime import timedelta

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.utils import timezone as djangotz
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import LoginAttempt
from .utils import get_client_ip


def _get_login_limit_config():
    """从 SystemConfig 读取登录限制参数，不存在则使用默认值。"""
    try:
        from system_config.models import SystemConfig
        max_attempts = SystemConfig.get_value("auth_max_login_attempts", 5)
        lockout_minutes = SystemConfig.get_value("auth_login_lockout_minutes", 15)
        return int(max_attempts), int(lockout_minutes)
    except Exception:
        return 5, 15


def _get_request_ip(context):
    """从 serializer context 中安全获取客户端 IP。"""
    request = context.get("request")
    if request:
        return get_client_ip(request)
    return "0.0.0.0"


class LoginSerializer(serializers.Serializer):
    """Accepts username + password, returns nothing — used only for validation.

    Enforces brute-force protection: after N consecutive failed logins from
    the same username+IP within a configurable window, subsequent attempts are
    rejected with a lockout message.
    """

    username = serializers.CharField()
    password = serializers.CharField(style={"input_type": "password"}, write_only=True)

    def validate(self, attrs):
        username = attrs.get("username")
        password = attrs.get("password")

        ip = _get_request_ip(self.context)
        max_attempts, lockout_minutes = _get_login_limit_config()
        cutoff = djangotz.now() - timedelta(minutes=lockout_minutes)

        # ── Check if this username+IP is locked out ──
        recent_failures = LoginAttempt.objects.filter(
            username=username,
            ip_address=ip,
            success=False,
            attempted_at__gte=cutoff,
        ).count()

        if recent_failures >= max_attempts:
            raise serializers.ValidationError(
                f"登录失败次数过多，请 {lockout_minutes} 分钟后重试。"
            )

        # ── Authenticate ──
        user = authenticate(username=username, password=password)

        if user is None:
            LoginAttempt.objects.create(username=username, ip_address=ip, success=False)
            raise serializers.ValidationError("用户名或密码错误。")

        if not user.is_active:
            LoginAttempt.objects.create(username=username, ip_address=ip, success=False)
            raise serializers.ValidationError("此账号已被禁用。")

        # Successful login
        LoginAttempt.objects.create(username=username, ip_address=ip, success=True)
        attrs["user"] = user
        return attrs


class TokenPairSerializer(TokenObtainPairSerializer):
    """Extended JWT token pair that includes user info in the response."""

    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user
        data["user"] = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_superuser": user.is_superuser,
        }
        return data


class UserSerializer(serializers.ModelSerializer):
    """User profile for the /me endpoint — includes permissions."""

    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "email", "is_superuser", "date_joined", "permissions"]

    def get_permissions(self, user):
        from .permissions import get_user_permissions
        return sorted(get_user_permissions(user))


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(style={"input_type": "password"}, write_only=True)
    new_password = serializers.CharField(
        style={"input_type": "password"}, write_only=True, min_length=6
    )

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("原密码不正确。")
        return value


# ═══════════════════════════════════════════════════════════════════
# Admin user management serializers
# ═══════════════════════════════════════════════════════════════════

class AdminUserListSerializer(serializers.ModelSerializer):
    """User list for admin page — includes failed attempt count + role info."""

    failed_attempts = serializers.SerializerMethodField()
    role_id = serializers.SerializerMethodField()
    role_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "is_active", "is_superuser",
            "date_joined", "last_login", "failed_attempts",
            "role_id", "role_name",
        ]

    def get_failed_attempts(self, user):
        """返回该用户最近的失败登录次数（当前锁定窗口内）。"""
        _, lockout_minutes = _get_login_limit_config()
        cutoff = djangotz.now() - timedelta(minutes=lockout_minutes)
        return LoginAttempt.objects.filter(
            username=user.username,
            success=False,
            attempted_at__gte=cutoff,
        ).count()

    def get_role_id(self, user):
        profile = getattr(user, "profile", None)
        if profile and profile.role:
            return profile.role_id
        return None

    def get_role_name(self, user):
        profile = getattr(user, "profile", None)
        if profile and profile.role:
            return profile.role.display_name
        return None


class AdminCreateUserSerializer(serializers.Serializer):
    """Create a new user (admin-only)."""

    username = serializers.CharField(min_length=1, max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(min_length=6, style={"input_type": "password"}, write_only=True)
    is_superuser = serializers.BooleanField(default=False)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("用户名已存在。")
        return value


class AdminResetPasswordSerializer(serializers.Serializer):
    """Force-reset another user's password (admin-only)."""

    new_password = serializers.CharField(
        min_length=6, style={"input_type": "password"}, write_only=True,
    )


class RoleSerializer(serializers.Serializer):
    """Serialize a UserRole for the admin API."""
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    permissions = serializers.ListField(child=serializers.CharField())
    is_builtin = serializers.BooleanField(read_only=True)
    user_count = serializers.IntegerField(read_only=True)


class RoleUpdateSerializer(serializers.Serializer):
    """Update a role's permission set."""
    permissions = serializers.ListField(child=serializers.CharField())


class UserRoleAssignmentSerializer(serializers.Serializer):
    """Assign a role to a user."""
    role_id = serializers.IntegerField(required=True)
