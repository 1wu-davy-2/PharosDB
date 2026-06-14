"""Create UserRole model and seed 3 built-in roles."""

from django.db import migrations, models


BUILTIN_ROLES = [
    {
        "name": "super_admin",
        "display_name": "超级管理员",
        "description": "拥有系统全部权限",
        "is_builtin": True,
    },
    {
        "name": "operator",
        "display_name": "运维人员",
        "description": "日常运维操作权限，可管理实例、告警规则、巡检等，不可管理系统用户和全局设置",
        "is_builtin": True,
    },
    {
        "name": "viewer",
        "display_name": "只读观察者",
        "description": "仅可查看各页面数据，不可执行任何修改操作",
        "is_builtin": True,
    },
]

# Import ROLE_PERMISSIONS inline since we can't import from models in a migration
ROLE_PERMISSIONS = {
    "super_admin": [
        "instances:view", "instances:create", "instances:edit",
        "instances:delete", "instances:test", "instances:collect",
        "qan:view", "qan:explain",
        "locks:view",
        "alerts:view", "alerts:create", "alerts:edit",
        "alerts:delete", "alerts:toggle",
        "advisor:view", "advisor:run", "advisor:toggle",
        "advisor:targeting", "advisor:groups",
        "settings:view", "settings:write",
        "system:view", "system:users",
    ],
    "operator": [
        "instances:view", "instances:create", "instances:edit",
        "instances:delete", "instances:test", "instances:collect",
        "qan:view", "qan:explain",
        "locks:view",
        "alerts:view", "alerts:create", "alerts:edit",
        "alerts:delete", "alerts:toggle",
        "advisor:view", "advisor:run", "advisor:toggle",
        "advisor:targeting", "advisor:groups",
        "settings:view",
    ],
    "viewer": [
        "instances:view",
        "qan:view",
        "locks:view",
        "alerts:view",
        "advisor:view",
        "settings:view",
    ],
}


def seed_roles(apps, schema_editor):
    UserRole = apps.get_model("accounts", "UserRole")
    for role_data in BUILTIN_ROLES:
        name = role_data["name"]
        role, _ = UserRole.objects.get_or_create(
            name=name,
            defaults={
                "display_name": role_data["display_name"],
                "description": role_data["description"],
                "is_builtin": role_data["is_builtin"],
                "permissions": ROLE_PERMISSIONS.get(name, []),
            },
        )
        # Update permissions on existing roles (idempotent re-run)
        if not _:
            role.permissions = ROLE_PERMISSIONS.get(name, [])
            role.save(update_fields=["permissions"])


def unseed_roles(apps, schema_editor):
    UserRole = apps.get_model("accounts", "UserRole")
    names = [r["name"] for r in BUILTIN_ROLES]
    UserRole.objects.filter(name__in=names).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_create_login_attempt"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserRole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(db_index=True, max_length=64, unique=True, verbose_name="角色标识")),
                ("display_name", models.CharField(max_length=128, verbose_name="显示名称")),
                ("description", models.TextField(blank=True, default="", verbose_name="描述")),
                ("permissions", models.JSONField(default=list, verbose_name="权限列表")),
                ("is_builtin", models.BooleanField(default=False, verbose_name="内置角色")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
            ],
            options={
                "verbose_name": "用户角色",
                "verbose_name_plural": "用户角色",
                "db_table": "accounts_user_role",
                "ordering": ["-is_builtin", "name"],
            },
        ),
        migrations.RunPython(seed_roles, unseed_roles),
    ]
