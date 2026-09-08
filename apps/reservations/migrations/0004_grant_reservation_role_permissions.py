"""Grant the booking permissions declared on ``Reservation.Meta`` to roles.

Booking is ordinary staff work, so every catalog role may book. Managing other
people's reservations follows the same scoped-administrator set as the space
catalog in ``0002``. Overriding policy with an audited reason is narrower: it
stays with the roles that carry management authority, not their assistants.
"""

from django.db import migrations

BOOK_ROLE_CODES = (
    "system_admin",
    "principal_broker",
    "broker_admin",
    "regional_manager",
    "regional_admin",
    "regional_transaction_coordinator",
    "branch_manager",
    "branch_admin",
    "transaction_coordinator",
    "realtor",
    "marketing_team",
    "accountant",
    "compliance",
    "it_support",
)

MANAGE_ROLE_CODES = (
    "system_admin",
    "principal_broker",
    "broker_admin",
    "regional_manager",
    "regional_admin",
    "branch_manager",
    "branch_admin",
)

OVERRIDE_ROLE_CODES = (
    "system_admin",
    "principal_broker",
    "broker_admin",
    "regional_manager",
    "branch_manager",
)

GRANTS = (
    ("book_spaces", BOOK_ROLE_CODES),
    ("manage_reservations", MANAGE_ROLE_CODES),
    ("override_reservations", OVERRIDE_ROLE_CODES),
)


def _ensure_reservation_permissions(apps) -> None:
    from django.apps import apps as global_apps
    from django.contrib.auth.management import create_permissions

    app_config = global_apps.get_app_config("reservations")
    if app_config.models_module is None:
        app_config.models_module = app_config.module
    create_permissions(app_config, apps=apps, verbosity=0)


def _apply(apps, *, add: bool) -> None:
    from apps.user.roles import ROLE_BY_KEY

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    if add:
        _ensure_reservation_permissions(apps)
    for codename, role_codes in GRANTS:
        permission = Permission.objects.filter(
            content_type__app_label="reservations", codename=codename
        ).first()
        if permission is None:
            continue
        for role_code in role_codes:
            definition = ROLE_BY_KEY.get(role_code)
            if definition is None:
                continue
            group = Group.objects.filter(name=definition.group_name).first()
            if group is None:
                continue
            if add:
                group.permissions.add(permission)
            else:
                group.permissions.remove(permission)


def grant(apps, schema_editor):
    _apply(apps, add=True)


def ungrant(apps, schema_editor):
    _apply(apps, add=False)


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0003_reservation_occupancy_ledger"),
        ("user", "0029_office_timezone"),
    ]

    operations = [migrations.RunPython(grant, ungrant)]
