"""Grant the Quick Access permissions and carry the shipped panel into data.

Before this migration the launcher panel was a tuple in
``apps.web.dashboard.providers``. Seeding those four rows as company-wide,
every-role links keeps every existing dashboard identical on the deploy that
turns the panel into administered data; nothing about what an agent sees
changes until an administrator changes it.
"""

from django.db import migrations

SCOPED = "manage_quick_access"
COMPANY = "manage_company_quick_access"

PERMISSION_NAMES = {
    SCOPED: "Can manage scoped Quick Access links",
    COMPANY: "Can manage company-wide Quick Access links",
}

GROUP_CODENAMES = {
    "Admins": (SCOPED, COMPANY),
    "Principal Broker": (SCOPED, COMPANY),
    "Broker Admin": (SCOPED, COMPANY),
    "Region Managers": (SCOPED,),
    "Regional Admin": (SCOPED,),
    "Branch Managers": (SCOPED,),
    "Branch Admin": (SCOPED,),
    "Marketing Team": (SCOPED,),
}

SEED_LINKS = (
    ("lofty", "Lofty", "https://www.lofty.com", "contact", 10),
    ("skyslope", "SkySlope", "https://www.skyslope.com", "shield-check", 20),
    (
        "microsoft365",
        "Microsoft 365",
        "https://www.microsoft365.com",
        "microsoft",
        30,
    ),
    ("dotloop", "Dotloop", "https://www.dotloop.com", "signature", 40),
)


def grant_permissions(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    content_type, _created = ContentType.objects.get_or_create(
        app_label="web", model="operationspermission"
    )
    permissions = {}
    for codename, name in PERMISSION_NAMES.items():
        permission, _created = Permission.objects.get_or_create(
            content_type=content_type,
            codename=codename,
            defaults={"name": name},
        )
        permissions[codename] = permission
    for group_name, codenames in GROUP_CODENAMES.items():
        group, _created = Group.objects.get_or_create(name=group_name)
        group.permissions.add(*(permissions[codename] for codename in codenames))


def revoke_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    permissions = list(
        Permission.objects.filter(
            content_type__app_label="web",
            content_type__model="operationspermission",
            codename__in=PERMISSION_NAMES,
        )
    )
    if not permissions:
        return
    for group in Group.objects.filter(name__in=GROUP_CODENAMES):
        group.permissions.remove(*permissions)


def seed_links(apps, schema_editor):
    QuickAccessLink = apps.get_model("web", "QuickAccessLink")
    for stable_key, name, url, icon, order in SEED_LINKS:
        QuickAccessLink.objects.get_or_create(
            stable_key=stable_key,
            defaults={
                "name": name,
                "description": "",
                "destination_type": "external_url",
                "destination_value": url,
                "icon": icon,
                "sort_order": order,
                "is_active": True,
                "company_wide": True,
                "owner_scope": "company",
                "sso_capability": "none",
                "integration_health": "unknown",
                "setup_behavior": "self_service",
            },
        )


def unseed_links(apps, schema_editor):
    QuickAccessLink = apps.get_model("web", "QuickAccessLink")
    QuickAccessLink.objects.filter(
        stable_key__in=[item[0] for item in SEED_LINKS]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("web", "0006_alter_operationspermission_options_quickaccesslink_and_more"),
    ]

    operations = [
        migrations.RunPython(grant_permissions, revoke_permissions),
        migrations.RunPython(seed_links, unseed_links),
    ]
