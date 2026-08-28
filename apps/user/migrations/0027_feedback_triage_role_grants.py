"""Grant the feedback triage permissions onto the roles that run the queue.

The other half of adding codenames to ``apps.user.roles``: role bundles reach
Django groups by migration, so an existing deployment's groups keep whatever
the last migration gave them.

Additive and idempotent — it grants, never revokes. A deployment that has
deliberately removed one of these keeps that decision.

``web.view_feedback`` is deliberately absent from the grants below even though
managers hold it: reading feedback in scope was already theirs, and triage is
the capability being added. Widening managers into the internal-note channel
here would be exactly the silent privilege growth these migrations exist to
avoid.
"""

from django.db import migrations

GRANTS: dict[str, tuple[str, ...]] = {
    "system_admin": ("triage_feedback", "assign_feedback", "note_feedback"),
    "principal_broker": ("triage_feedback", "assign_feedback", "note_feedback"),
    "broker_admin": ("triage_feedback", "assign_feedback", "note_feedback"),
    "it_support": (
        "view_feedback",
        "triage_feedback",
        "assign_feedback",
        "note_feedback",
    ),
}


def _ensure_web_permissions(apps) -> None:
    """Create the ``web`` permission rows now rather than after the whole run.

    Django builds ``Permission`` rows in a ``post_migrate`` hook, so a data
    migration granting a permission added in the same run finds nothing to
    grant. Calling the creator directly is the documented way out.
    """
    from django.apps import apps as global_apps
    from django.contrib.auth.management import create_permissions

    app_config = global_apps.get_app_config("web")
    if app_config.models_module is None:
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
                content_type__app_label="web", codename__in=codenames
            )
        )


class Migration(migrations.Migration):
    dependencies = [
        ("user", "0026_operational_task_role_grants"),
        ("web", "0016_alter_operationspermission_options"),
    ]

    operations = [migrations.RunPython(grant, ungrant)]
