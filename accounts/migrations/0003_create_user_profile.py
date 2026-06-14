"""Create UserProfile model — extends auth.User with role FK."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0002_create_user_role"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="profile",
                    to=settings.AUTH_USER_MODEL,
                    verbose_name="用户",
                )),
                ("role", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="users",
                    to="accounts.userrole",
                    verbose_name="角色",
                )),
            ],
            options={
                "verbose_name": "用户资料",
                "verbose_name_plural": "用户资料",
                "db_table": "accounts_user_profile",
            },
        ),
    ]
