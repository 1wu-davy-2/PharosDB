"""
RBAC permission helpers — resolve user permissions from role and enforce via DRF.
"""

from rest_framework.permissions import BasePermission

from .models import ALL_PERMISSIONS_SET


def get_user_permissions(user) -> set:
    """Return the permission code set for a user.

    Superusers always get the full set.
    Other users get permissions from their assigned role (if any).
    """
    if not user or not user.is_authenticated:
        return set()

    # Superusers have all permissions
    if user.is_superuser:
        return ALL_PERMISSIONS_SET.copy()

    # Check role via profile
    profile = getattr(user, "profile", None)
    if profile and profile.role:
        return set(profile.role.permissions)

    return set()


def user_has_permission(user, permission_code: str) -> bool:
    """Check whether the user holds a specific permission code."""
    return permission_code in get_user_permissions(user)


class HasPermission(BasePermission):
    """DRF permission class that checks a view's `required_permission` attribute.

    Usage for simple APIViews (single action):
        class MyView(APIView):
            required_permission = "instances:delete"

    Usage for ViewSets (per-action mapping):
        class MyViewSet(ModelViewSet):
            permission_map = {
                "create": "instances:create",
                "update": "instances:edit",
                "partial_update": "instances:edit",
                "destroy": "instances:delete",
            }

    If neither `permission_map[action]` nor `required_permission` is set,
    the check passes (no specific permission required beyond authentication).
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        permission_map = getattr(view, "permission_map", None)
        if permission_map is not None:
            # ViewSets have `.action` (e.g. "create", "destroy")
            action = getattr(view, "action", None)
            if action is not None:
                code = permission_map.get(action)
                if code is not None:
                    return user_has_permission(request.user, code)
                # action not in map → fall through

            # APIViews use HTTP method as key (e.g. "GET", "POST")
            if action is None:
                code = permission_map.get(request.method)
                if code is not None:
                    return user_has_permission(request.user, code)
                # method not in map → fall through

        # Single permission code (for APIViews with one action)
        code = getattr(view, "required_permission", None)
        if code is not None:
            return user_has_permission(request.user, code)

        return True  # no specific permission — any authenticated user
