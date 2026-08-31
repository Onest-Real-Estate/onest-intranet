"""Grant reservation administration permissions onto manager role groups.

Additive and idempotent. Agents reserve for themselves without these grants.
"""

from django.db import migrations

GRANTS: dict[str, tuple[str, ...]] = {
    "system_admin": (
        "reserve_on_behalf",
        "approve_reservations",
        "override_reservations",
    ),
    "principal_broker": (
        "reserve_on_behalf",
        "approve_reservations",
        "override_reservations",
    ),
    "broker_admin": (
        "reserve_on_behalf",
        "approve_reservations",
        "override_reservations",
    ),
    "regional_manager": (
        "reserve_on_behalf",
        "approve_reservations",
        "override_reservations",
    ),
    "branch_manager": (
        "reserve_on_behalf",
        "approve_reservations",
        "override_reservations",
    ),
    "regional_admin": ("approve_reservations",),
    "branch_admin": ("approve_reservations",),
}


def _ensure_inventory_permissions(apps) -> None:
    from django.apps import apps as global_apps
    from django.contrib.auth.management import create_permissions

    app_config = global_apps.get_app_config("inventory")
    if app_config.models_module is None:
        app_config.models_module = app_config.module
    create_permissions(app_config, apps=apps, verbosity=0)


def grant(apps, schema_editor):
    from apps.user.roles import ROLE_BY_KEY

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    _ensure_inventory_permissions(apps)
    by_codename = {
        permission.codename: permission
        for permission in Permission.objects.filter(
            content_type__app_label="inventory",
            codename__in=sorted({c for codes in GRANTS.values() for c in codes}),
        )
    }
    for role_code, codenames in GRANTS.items():
        definition = ROLE_BY_KEY.get(role_code)
        if definition is None:
            continue
        group = Group.objects.filter(name=definition.group_name).first()
        if group is None:
            continue
        wanted = [by_codename[c] for c in codenames if c in by_codename]
        if wanted:
            group.permissions.add(*wanted)


def ungrant(apps, schema_editor):
    from apps.user.roles import ROLE_BY_KEY

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    for role_code, codenames in GRANTS.items():
        definition = ROLE_BY_KEY.get(role_code)
        if definition is None:
            continue
        group = Group.objects.filter(name=definition.group_name).first()
        if group is None:
            continue
        group.permissions.remove(
            *Permission.objects.filter(
                content_type__app_label="inventory", codename__in=codenames
            )
        )


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0002_inventory_reservations"),
        ("user", "0028_inventory_role_grants"),
    ]

    operations = [
        migrations.RunPython(grant, ungrant),
    ]
