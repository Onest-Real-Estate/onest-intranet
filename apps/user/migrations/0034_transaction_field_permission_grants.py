"""Grant transaction field permissions onto the roles that own deal data.

Role bundles reach Django groups by migration, so adding codenames to
``apps.user.roles`` is only half the change. Additive and idempotent.
"""

from django.db import migrations

GRANTS: dict[str, tuple[str, ...]] = {
    "system_admin": (
        "view_transaction_financials",
        "view_transaction_clients",
    ),
    "principal_broker": (
        "view_transaction_financials",
        "view_transaction_clients",
    ),
    "broker_admin": (
        "view_transaction_financials",
        "view_transaction_clients",
    ),
    "regional_manager": (
        "view_transaction_financials",
        "view_transaction_clients",
    ),
    "regional_transaction_coordinator": (
        "view_transaction_financials",
        "view_transaction_clients",
    ),
    "transaction_coordinator": (
        "view_transaction_financials",
        "view_transaction_clients",
    ),
    "accountant": ("view_transaction_financials",),
}


def _ensure_transaction_permissions(apps) -> None:
    from django.apps import apps as global_apps
    from django.contrib.auth.management import create_permissions

    app_config = global_apps.get_app_config("transactions")
    if app_config.models_module is None:
        app_config.models_module = app_config.module
    create_permissions(app_config, apps=apps, verbosity=0)


def grant(apps, schema_editor):
    from apps.user.roles import ROLE_BY_KEY

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    _ensure_transaction_permissions(apps)
    by_codename = {
        permission.codename: permission
        for permission in Permission.objects.filter(
            content_type__app_label="transactions",
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
                content_type__app_label="transactions", codename__in=codenames
            )
        )


class Migration(migrations.Migration):
    dependencies = [
        ("user", "0033_onboardingstreamstate"),
        ("transactions", "0001_transaction_domain"),
    ]

    operations = [migrations.RunPython(grant, ungrant)]
