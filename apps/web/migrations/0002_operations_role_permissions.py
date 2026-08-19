from django.db import migrations


PERMISSION_NAMES = {
    "view_users": "Can view scoped users",
    "view_new_agents": "Can view scoped new agents",
    "add_users": "Can add users",
    "assign_user_roles": "Can assign user roles",
    "view_agent_contracts": "Can view scoped agent contracts",
    "view_transactions": "Can view scoped transactions",
    "view_inventory": "Can view scoped inventory",
    "view_reservations": "Can view scoped reservations",
    "manage_announcements": "Can manage announcements",
    "manage_training": "Can manage training",
    "manage_documents": "Can manage documents",
    "view_compliance": "Can view scoped compliance items",
    "view_feedback": "Can view scoped feedback",
    "view_platform_tasks": "Can view sanitized platform task status",
    "manage_offices": "Can manage scoped offices",
    "view_it_support": "Can view scoped IT support requests",
}

ROLE_CODENAMES = {
    "Admins": frozenset(PERMISSION_NAMES),
    "Region Managers": frozenset(
        {
            "view_users",
            "view_new_agents",
            "view_transactions",
            "view_inventory",
            "view_reservations",
            "manage_training",
            "manage_documents",
            "view_feedback",
            "manage_offices",
        }
    ),
    "Branch Managers": frozenset(
        {
            "view_users",
            "view_new_agents",
            "view_inventory",
            "view_reservations",
            "manage_training",
            "manage_documents",
            "view_feedback",
            "manage_offices",
        }
    ),
}


def grant_operations_permissions(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    content_type, _ = ContentType.objects.get_or_create(
        app_label="web",
        model="operationspermission",
    )
    permissions = {}
    for codename, name in PERMISSION_NAMES.items():
        permission, _ = Permission.objects.get_or_create(
            content_type=content_type,
            codename=codename,
            defaults={"name": name},
        )
        permissions[codename] = permission
    for group_name, codenames in ROLE_CODENAMES.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        group.permissions.add(*(permissions[codename] for codename in codenames))


def revoke_operations_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    permissions = Permission.objects.filter(
        content_type__app_label="web",
        content_type__model="operationspermission",
        codename__in=PERMISSION_NAMES,
    )
    for group_name in ROLE_CODENAMES:
        group = Group.objects.filter(name=group_name).first()
        if group is not None:
            group.permissions.remove(*permissions)


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        (
            "user",
            "0010_remove_userroleassignment_user_role_assignment_company_scope_empty_and_more",
        ),
        ("web", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            grant_operations_permissions,
            revoke_operations_permissions,
        ),
    ]
