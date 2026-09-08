"""Add user-facing activity timeline permission and grant default roles."""

from django.db import migrations

PERMISSION_CODENAME = "can_view_activity_timeline"
PERMISSION_NAME = "Can view user-facing activity timelines"

# Group names matching apps.user.roles ROLE_DEFINITIONS.group_name for the
# catalog default_roles of audit.can_view_activity_timeline.
GRANT_GROUPS = (
    "Admins",
    "Principal Broker",
    "Broker Admin",
    "Region Managers",
    "Regional Admin",
    "Regional Transaction Coordinator",
    "Branch Managers",
    "Branch Admin",
    "Transaction Coordinator",
    "Accountant",
    "Compliance",
    "IT Support",
)


def grant_permission(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    content_type, _ = ContentType.objects.get_or_create(
        app_label="audit",
        model="auditevent",
    )
    permission, _ = Permission.objects.get_or_create(
        content_type=content_type,
        codename=PERMISSION_CODENAME,
        defaults={"name": PERMISSION_NAME},
    )
    for group_name in GRANT_GROUPS:
        group, _ = Group.objects.get_or_create(name=group_name)
        group.permissions.add(permission)


def revoke_permission(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    permission = Permission.objects.filter(
        content_type__app_label="audit",
        content_type__model="auditevent",
        codename=PERMISSION_CODENAME,
    ).first()
    if permission is None:
        return
    for group in Group.objects.all():
        group.permissions.remove(permission)


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0002_auditevent"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="auditevent",
            options={
                "ordering": ["-occurred_at", "-recorded_at"],
                "permissions": [
                    ("can_view_audit_events", "Can view audit events"),
                    ("can_export_audit_events", "Can export audit events"),
                    (
                        "can_view_activity_timeline",
                        "Can view user-facing activity timelines",
                    ),
                ],
                "verbose_name": "audit event",
                "verbose_name_plural": "audit events",
            },
        ),
        migrations.RunPython(grant_permission, revoke_permission),
    ]
