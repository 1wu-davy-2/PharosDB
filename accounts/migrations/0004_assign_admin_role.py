"""Assign super_admin role to existing admin (id=1) on migrate."""

from django.db import migrations


def assign_admin_role(apps, schema_editor):
    User = apps.get_model("auth", "User")
    UserProfile = apps.get_model("accounts", "UserProfile")
    UserRole = apps.get_model("accounts", "UserRole")

    try:
        admin = User.objects.get(pk=1)
    except User.DoesNotExist:
        return

    try:
        role = UserRole.objects.get(name="super_admin")
    except UserRole.DoesNotExist:
        return

    UserProfile.objects.get_or_create(user=admin, defaults={"role": role})
    # Ensure the role is set even if profile already existed
    UserProfile.objects.filter(user=admin).update(role=role)


def unassign_admin_role(apps, schema_editor):
    UserProfile = apps.get_model("accounts", "UserProfile")
    UserProfile.objects.filter(user_id=1).update(role=None)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_create_user_profile"),
    ]

    operations = [
        migrations.RunPython(assign_admin_role, unassign_admin_role),
    ]
