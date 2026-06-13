"""
Accounts app views — login / logout / me / change-password.
"""
from rest_framework import generics, permissions, status, views
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    UserSerializer,
)
from .utils import get_client_ip, get_client_ip_info


class LoginView(views.APIView):
    """POST /api/auth/login/ — returns JWT access + refresh tokens (IP-bound)."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
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
