"""系统配置 REST API — 全局参数的读写接口。"""

from rest_framework import permissions, status, views
from rest_framework.response import Response

from .models import SystemConfig
from .serializers import SystemConfigSerializer


class IsSuperAdmin(permissions.BasePermission):
    """仅超级管理员可修改全局配置，普通用户只读。"""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        return (
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser
        )


class ConfigView(views.APIView):
    """GET/PUT /api/config/ — 查询或批量更新全局配置。"""

    permission_classes = [IsSuperAdmin]

    def get(self, request):
        """获取所有配置项（按分类排序）。"""
        qs = SystemConfig.objects.all().order_by("category", "key")
        data = [
            {
                "key": c.key,
                "value": c.to_typed(),
                "value_type": c.value_type,
                "display_name": c.display_name,
                "description": c.description,
                "category": c.category,
                "editable": c.editable,
            }
            for c in qs
        ]
        return Response({"configs": data})

    def put(self, request):
        """批量更新配置项。

        请求体: {"configs": [{"key": "top_n_explain", "value": "10"}, ...]}
        非 editable 的 key 会被拒绝。
        """
        items = request.data.get("configs", [])
        if not items:
            return Response({"error": "请提供 configs 数组"}, status=400)

        updated = []
        errors = []
        for item in items:
            key = item.get("key")
            new_val = item.get("value")
            if not key:
                errors.append({"key": key, "error": "缺少 key"})
                continue
            try:
                cfg = SystemConfig.objects.get(key=key)
                if not cfg.editable:
                    errors.append({"key": key, "error": "该项不允许修改"})
                    continue
                cfg.value = str(new_val)
                cfg.save(update_fields=["value", "updated_at"])
                updated.append({
                    "key": cfg.key,
                    "value": cfg.to_typed(),
                    "value_type": cfg.value_type,
                    "display_name": cfg.display_name,
                })
            except SystemConfig.DoesNotExist:
                errors.append({"key": key, "error": "配置项不存在"})

        return Response({"updated": updated, "errors": errors})
