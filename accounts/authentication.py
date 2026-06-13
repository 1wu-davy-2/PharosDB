"""
PharosDB custom JWT authentication — IP-bound token validation.

Every authenticated request verifies that the client IP matches the IP
embedded in the JWT at login time.  If they differ the token is rejected
with a 403 so a stolen token cannot be replayed from a different host.
"""
import logging

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from .utils import get_client_ip

logger = logging.getLogger(__name__)


class IPMismatchError(PermissionDenied):
    """403 — token is valid but was issued to a different IP."""
    default_detail = "Token IP 绑定验证失败：请求 IP 与签发 IP 不匹配。"
    default_code = "ip_mismatch"


class PharosJWTAuthentication(JWTAuthentication):
    """Drop-in replacement for JWTAuthentication that enforces IP binding.

    Invalid token                 → 401 Unauthorized (same as SimpleJWT)
    Valid token, different IP     → 403 Forbidden  (IP binding violation)
    No ``ip`` claim in token      → allowed         (backward-compat transition)
    """

    def authenticate(self, request):
        try:
            result = super().authenticate(request)
        except AuthenticationFailed:
            raise
        except Exception as exc:
            # Convert any non-APIException (e.g. from token backend) to
            # proper DRF AuthenticationFailed so it returns 401, not 500.
            logger.warning("JWT authentication error: %s", exc)
            raise AuthenticationFailed(str(exc))

        if result is None:
            return None

        user, validated_token = result
        token_ip = validated_token.get("ip")

        if token_ip is not None:
            request_ip = get_client_ip(request)
            if request_ip != token_ip:
                raise IPMismatchError(
                    f"Token IP 绑定验证失败：token 签发 IP ({token_ip}) "
                    f"与请求 IP ({request_ip}) 不匹配，可能存在 token 盗用。"
                )

        return (user, validated_token)
