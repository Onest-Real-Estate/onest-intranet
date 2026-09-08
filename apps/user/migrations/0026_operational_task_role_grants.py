"""Grant the operational-task permissions onto the roles that own the queue.

Role bundles are seeded onto Django groups by migration, so adding a codename
to ``apps.user.roles`` is only half the change — an existing deployment's
groups keep whatever the last migration gave them. This is the other half.

Additive and idempotent: it grants, never revokes. A deployment that has
deliberately removed one of these from a group keeps that decision, and a
re-run is a no-op.

Deliberately **not** granted alongside ``web.view_platform_tasks``. That
permission means "read sanitized Celery job status" and is held by roles that
were never given a scoped work queue; widening it here is exactly the silent
privilege growth this module was named to avoid.
"""

from django.db import migrations

#: role code → the task permissions that role should hold.
GRANTS: dict[str, tuple[str, ...]] = {
    "system_admin": (
        "view_operational_tasks",
        "manage_operational_tasks",
        "assign_operational_tasks",
        "comment_operational_tasks",
    ),
    "principal_broker": (
        "view_operational_tasks",
        "manage_operational_tasks",
        "assign_operational_tasks",
        "comment_operational_tasks",
    ),
    "broker_admin": (
        "view_operational_tasks",
        "manage_operational_tasks",
        "assign_operational_tasks",
        "comment_operational_tasks",
    ),
    "it_support": (
        "view_operational_tasks",
        "manage_operational_tasks",
        "assign_operational_tasks",
        "comment_operational_tasks",
    ),
    # Managers route and discuss work in their scope but do not own closing it
    # or the internal-note channel, both of which need the management grant.
    "regional_manager": (
        "view_operational_tasks",
        "assign_operational_tasks",
        "comment_operational_tasks",
    ),
    "branch_manager": (
        "view_operational_tasks",
        "assign_operational_tasks",
        "comment_operational_tasks",
    ),
}


def _ensure_web_permissions(apps) -> None:
    """Create the ``web`` permission rows now rather than after every migration.

    Django builds ``Permission`` rows in a ``post_migrate`` hook, which runs
    only once the whole run finishes. A data migration that grants a permission
    added in the same run therefore finds nothing to grant. Calling the
    creator directly is the documented way out.
    """
    from django.apps import apps as global_apps
    from django.contrib.auth.management import create_permissions

    app_config = global_apps.get_app_config("web")
    if app_config.models_module is None:
        # ``create_permissions`` short-circuits on a config with no models
        # module. The app has models; this only matters when the registry has
        # not attached them yet at migration time.
        app_config.models_module = app_config.module
    create_permissions(app_config, apps=apps, verbosity=0)


def grant(apps, schema_editor):
    from apps.user.roles import ROLE_BY_KEY

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    _ensure_web_permissions(apps)

    by_codename = {
        permission.codename: permission
        for permission in Permission.objects.filter(
            content_type__app_label="web",
            codename__in=sorted(
                {codename for codenames in GRANTS.values() for codename in codenames}
            ),
        )
    }
    if not by_codename:  # pragma: no cover - defensive
        return

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
    """Reverse cleanly so the migration can be rolled back in a review branch."""
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
                content_type__app_label="web", codename__in=codenames
            )
        )


class Migration(migrations.Migration):
    dependencies = [
        ("user", "0025_search_indexes"),
        ("web", "0013_alter_operationspermission_options"),
    ]

    operations = [migrations.RunPython(grant, ungrant)]
