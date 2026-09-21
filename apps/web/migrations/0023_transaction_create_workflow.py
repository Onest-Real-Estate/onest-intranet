"""Register create_own_transactions and grant create/manage role expansions."""

from django.db import migrations

CREATE_OWN = (
    "create_own_transactions",
    "Can create own transactions as primary agent",
)

MANAGE_GROUPS = ("Branch Managers",)
CREATE_OWN_GROUPS = ("Users",)


def grant(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    content_type, _ = ContentType.objects.get_or_create(
        app_label="web",
        model="operationspermission",
    )
    create_own, _ = Permission.objects.get_or_create(
        content_type=content_type,
        codename=CREATE_OWN[0],
        defaults={"name": CREATE_OWN[1]},
    )
    if create_own.name != CREATE_OWN[1]:
        create_own.name = CREATE_OWN[1]
        create_own.save(update_fields=["name"])

    manage = Permission.objects.filter(
        content_type=content_type,
        codename="manage_transactions",
    ).first()

    for group_name in CREATE_OWN_GROUPS:
        group, _ = Group.objects.get_or_create(name=group_name)
        group.permissions.add(create_own)
    if manage is not None:
        for group_name in MANAGE_GROUPS:
            group, _ = Group.objects.get_or_create(name=group_name)
            group.permissions.add(manage)


def ungrant(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    create_own = Permission.objects.filter(
        content_type__app_label="web",
        content_type__model="operationspermission",
        codename=CREATE_OWN[0],
    ).first()
    manage = Permission.objects.filter(
        content_type__app_label="web",
        content_type__model="operationspermission",
        codename="manage_transactions",
    ).first()
    if create_own is not None:
        for group_name in CREATE_OWN_GROUPS:
            group = Group.objects.filter(name=group_name).first()
            if group is not None:
                group.permissions.remove(create_own)
        create_own.delete()
    if manage is not None:
        for group_name in MANAGE_GROUPS:
            group = Group.objects.filter(name=group_name).first()
            if group is not None:
                group.permissions.remove(manage)


class Migration(migrations.Migration):
    dependencies = [
        ("web", "0022_transaction_domain"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="operationspermission",
            options={
                "default_permissions": (),
                "managed": False,
                "permissions": (
                    ("view_users", "Can view scoped users"),
                    ("view_new_agents", "Can view scoped new agents"),
                    (
                        "manage_new_agent_onboarding",
                        "Can manage scoped new-agent onboarding",
                    ),
                    ("add_users", "Can add users"),
                    ("assign_user_roles", "Can assign user roles"),
                    ("view_agent_contracts", "Can view scoped agent contracts"),
                    ("view_transactions", "Can view scoped transactions"),
                    (
                        "manage_transactions",
                        "Can create and manage scoped transactions",
                    ),
                    (
                        "create_own_transactions",
                        "Can create own transactions as primary agent",
                    ),
                    (
                        "transition_transactions",
                        "Can transition scoped transaction lifecycle",
                    ),
                    ("view_inventory", "Can view scoped inventory"),
                    ("view_reservations", "Can view scoped reservations"),
                    ("manage_announcements", "Can manage announcements"),
                    (
                        "publish_announcements",
                        "Can publish, schedule, and archive announcements",
                    ),
                    ("pin_announcements", "Can pin announcements"),
                    ("manage_training", "Can manage training"),
                    (
                        "manage_marketing_resources",
                        "Can manage marketing resources",
                    ),
                    (
                        "publish_marketing_resources",
                        "Can publish, schedule, and archive marketing resources",
                    ),
                    (
                        "download_marketing_sources",
                        "Can download marketing source files",
                    ),
                    ("manage_documents", "Can manage documents"),
                    (
                        "publish_documents",
                        "Can publish, schedule, and supersede documents",
                    ),
                    ("retire_documents", "Can retire published documents"),
                    ("view_compliance", "Can view scoped compliance items"),
                    ("manage_policies", "Can manage policies"),
                    ("approve_policies", "Can approve policies"),
                    (
                        "publish_policies",
                        "Can publish and retire policies",
                    ),
                    (
                        "view_policy_acknowledgements",
                        "Can view scoped policy acknowledgements",
                    ),
                    (
                        "waive_policy_acknowledgements",
                        "Can waive policy acknowledgements",
                    ),
                    ("view_feedback", "Can view scoped feedback"),
                    ("triage_feedback", "Can triage scoped feedback"),
                    ("assign_feedback", "Can assign feedback tickets"),
                    ("note_feedback", "Can write internal notes on feedback"),
                    (
                        "view_platform_tasks",
                        "Can view sanitized platform task status",
                    ),
                    (
                        "view_operational_tasks",
                        "Can view scoped operational tasks",
                    ),
                    (
                        "manage_operational_tasks",
                        "Can create and transition operational tasks",
                    ),
                    (
                        "assign_operational_tasks",
                        "Can assign operational tasks",
                    ),
                    (
                        "comment_operational_tasks",
                        "Can comment on operational tasks",
                    ),
                    ("manage_offices", "Can manage scoped offices"),
                    (
                        "manage_onboarding_tools",
                        "Can manage the agent tool catalog",
                    ),
                    ("view_it_support", "Can view scoped IT support requests"),
                    (
                        "triage_it_support",
                        "Can triage scoped IT support requests",
                    ),
                    ("assign_it_support", "Can assign IT support requests"),
                    (
                        "note_it_support",
                        "Can write internal notes on IT support requests",
                    ),
                    (
                        "manage_quick_access",
                        "Can manage scoped Quick Access links",
                    ),
                    (
                        "manage_company_quick_access",
                        "Can manage company-wide Quick Access links",
                    ),
                    ("view_reports", "Can view the operational reports catalog"),
                    ("export_reports", "Can export operational reports"),
                ),
            },
        ),
        migrations.RunPython(grant, ungrant),
    ]
