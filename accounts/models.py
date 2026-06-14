"""Accounts models — login attempt tracking, RBAC roles & user profiles."""

from django.conf import settings
from django.db import models


# ═══════════════════════════════════════════════════════════════════
# Permission codes — full registry
# ═══════════════════════════════════════════════════════════════════

ALL_PERMISSIONS = [
    # Instances
    "instances:view",
    "instances:create",
    "instances:edit",
    "instances:delete",
    "instances:test",
    "instances:collect",
    # QAN
    "qan:view",
    "qan:explain",
    # Locks
    "locks:view",
    # Alerts
    "alerts:view",
    "alerts:create",
    "alerts:edit",
    "alerts:delete",
    "alerts:toggle",
    # Advisor
    "advisor:view",
    "advisor:run",
    "advisor:toggle",
    "advisor:targeting",
    "advisor:groups",
    # Settings
    "settings:view",
    "settings:write",
    # System
    "system:view",
    "system:users",
]

ALL_PERMISSIONS_SET = set(ALL_PERMISSIONS)

# Permission groups for frontend checkbox rendering
PERMISSION_GROUPS = [
    {
        "name": "实例管理",
        "name_en": "Instances",
        "permissions": [
            {"code": "instances:view", "label": "查看实例", "label_en": "View"},
            {"code": "instances:create", "label": "注册实例", "label_en": "Create"},
            {"code": "instances:edit", "label": "编辑实例", "label_en": "Edit"},
            {"code": "instances:delete", "label": "删除实例", "label_en": "Delete"},
            {"code": "instances:test", "label": "连接测试", "label_en": "Test"},
            {"code": "instances:collect", "label": "手动采集", "label_en": "Collect"},
        ],
    },
    {
        "name": "SQL 分析",
        "name_en": "QAN",
        "permissions": [
            {"code": "qan:view", "label": "查看查询分析", "label_en": "View"},
            {"code": "qan:explain", "label": "手动 EXPLAIN", "label_en": "Explain"},
        ],
    },
    {
        "name": "锁分析",
        "name_en": "Locks",
        "permissions": [
            {"code": "locks:view", "label": "查看锁分析", "label_en": "View"},
        ],
    },
    {
        "name": "告警中心",
        "name_en": "Alerts",
        "permissions": [
            {"code": "alerts:view", "label": "查看告警", "label_en": "View"},
            {"code": "alerts:create", "label": "创建规则", "label_en": "Create"},
            {"code": "alerts:edit", "label": "编辑规则", "label_en": "Edit"},
            {"code": "alerts:delete", "label": "删除规则", "label_en": "Delete"},
            {"code": "alerts:toggle", "label": "启用/禁用规则", "label_en": "Toggle"},
        ],
    },
    {
        "name": "安全巡检",
        "name_en": "Advisor",
        "permissions": [
            {"code": "advisor:view", "label": "查看巡检", "label_en": "View"},
            {"code": "advisor:run", "label": "执行巡检", "label_en": "Run"},
            {"code": "advisor:toggle", "label": "启用/禁用规则", "label_en": "Toggle"},
            {"code": "advisor:targeting", "label": "配置目标分组", "label_en": "Targeting"},
            {"code": "advisor:groups", "label": "管理实例分组", "label_en": "Groups"},
        ],
    },
    {
        "name": "全局设置",
        "name_en": "Settings",
        "permissions": [
            {"code": "settings:view", "label": "查看设置", "label_en": "View"},
            {"code": "settings:write", "label": "修改设置", "label_en": "Write"},
        ],
    },
    {
        "name": "系统管理",
        "name_en": "System",
        "permissions": [
            {"code": "system:view", "label": "查看系统管理", "label_en": "View"},
            {"code": "system:users", "label": "管理用户", "label_en": "Users"},
        ],
    },
]

# Pre-built permission sets for built-in roles
ROLE_PERMISSIONS = {
    "super_admin": ALL_PERMISSIONS_SET,
    "operator": {
        "instances:view", "instances:create", "instances:edit",
        "instances:delete", "instances:test", "instances:collect",
        "qan:view", "qan:explain",
        "locks:view",
        "alerts:view", "alerts:create", "alerts:edit",
        "alerts:delete", "alerts:toggle",
        "advisor:view", "advisor:run", "advisor:toggle",
        "advisor:targeting", "advisor:groups",
        "settings:view",
    },
    "viewer": {
        "instances:view",
        "qan:view",
        "locks:view",
        "alerts:view",
        "advisor:view",
        "settings:view",
    },
}


# ═══════════════════════════════════════════════════════════════════
# Models
# ═══════════════════════════════════════════════════════════════════

class UserRole(models.Model):
    """用户角色 — 定义一组权限集合。"""

    name = models.CharField("角色标识", max_length=64, unique=True, db_index=True)
    display_name = models.CharField("显示名称", max_length=128)
    description = models.TextField("描述", blank=True, default="")
    permissions = models.JSONField("权限列表", default=list)
    is_builtin = models.BooleanField("内置角色", default=False)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "accounts_user_role"
        verbose_name = "用户角色"
        verbose_name_plural = verbose_name
        ordering = ["-is_builtin", "name"]

    def __str__(self):
        return self.display_name


class UserProfile(models.Model):
    """用户扩展资料 — 关联角色。"""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="用户",
    )
    role = models.ForeignKey(
        UserRole,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="users",
        verbose_name="角色",
    )

    class Meta:
        db_table = "accounts_user_profile"
        verbose_name = "用户资料"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.user.username} — {self.role.display_name if self.role else '无角色'}"


class LoginAttempt(models.Model):
    """记录每次登录尝试，用于检测暴力破解并锁定账号。

    锁定策略：同一用户名 + IP 在时间窗口内连续失败 N 次后拒绝后续尝试。
    N（默认 5）和窗口（默认 15 分钟）可通过 SystemConfig 配置。
    """

    username = models.CharField("用户名", max_length=150, db_index=True)
    ip_address = models.CharField("客户端 IP", max_length=64, default="0.0.0.0")
    success = models.BooleanField("是否成功", default=False)
    attempted_at = models.DateTimeField("尝试时间", auto_now_add=True, db_index=True)

    class Meta:
        db_table = "accounts_login_attempt"
        verbose_name = "登录尝试记录"
        verbose_name_plural = verbose_name
        ordering = ["-attempted_at"]

    def __str__(self):
        status = "成功" if self.success else "失败"
        return f"{self.username} @ {self.ip_address} — {status}"
