"""Fold the legacy four-value checklist into the catalog.

``user.OnboardingToolSetup`` held one row per agent per *enum* tool, which is
the shape this app replaced: adding a tool meant a deploy, and the operational
composer and My Tools disagreed because they read different tables.

This migration moves what those rows knew into ``AgentToolStatus`` and leaves
the legacy table untouched, so a rollback loses nothing. Both sides may already
hold a row for the same agent and tool, so the merge is deterministic rather
than last-writer-wins: the further-along state survives, and ties go to the
more recently updated row.
"""

from django.db import migrations

#: Legacy enum value → catalog slug. ``dotloop`` has no catalog row: the
#: brokerage retired it in favour of SkySlope (see web/0014), so those rows are
#: left where they are rather than being invented into a tool nobody uses.
LEGACY_SLUGS = {
    "lofty": "lofty",
    "skyslope": "skyslope",
    "microsoft365": "office-365",
}

#: Legacy state → catalog state. "Not required" is the catalog's
#: "not applicable": somebody excused from a tool, which still counts settled.
LEGACY_STATES = {
    "not_started": "not_started",
    "in_progress": "in_progress",
    "ready": "ready",
    "blocked": "blocked",
    "not_required": "not_applicable",
}

#: How far along a state is, for deciding which of two rows wins. Ready is the
#: end of the ladder; "not applicable" is settled but is not an achievement.
PRECEDENCE = {
    "not_started": 0,
    "requested": 1,
    "invitation_sent": 2,
    "in_progress": 3,
    "blocked": 3,
    "not_applicable": 4,
    "ready": 5,
}


def migrate_legacy_tool_setups(apps, schema_editor):
    OnboardingToolSetup = apps.get_model("user", "OnboardingToolSetup")
    OnboardingTool = apps.get_model("onboarding_tools", "OnboardingTool")
    AgentToolStatus = apps.get_model("onboarding_tools", "AgentToolStatus")

    tools = {
        tool.slug: tool
        for tool in OnboardingTool.objects.filter(slug__in=set(LEGACY_SLUGS.values()))
    }
    if not tools:
        return

    legacy = (
        OnboardingToolSetup.objects.filter(tool__in=LEGACY_SLUGS)
        .select_related("case")
        .order_by("pk")
        .iterator(chunk_size=500)
    )
    for setup in legacy:
        tool = tools.get(LEGACY_SLUGS[setup.tool])
        state = LEGACY_STATES.get(setup.state)
        if tool is None or state is None:
            continue
        agent_id = setup.case.user_id
        existing = AgentToolStatus.objects.filter(agent_id=agent_id, tool=tool).first()
        if existing is not None:
            keeps_existing = PRECEDENCE[existing.state] > PRECEDENCE[state] or (
                PRECEDENCE[existing.state] == PRECEDENCE[state]
                and existing.updated_at >= setup.updated_at
            )
            if keeps_existing:
                continue
            existing.state = state
            existing.updated_by_id = setup.updated_by_id
            # ``ready`` and a readiness timestamp travel together; the legacy
            # row's own timestamp is the only honest answer available.
            existing.ready_at = setup.updated_at if state == "ready" else None
            existing.save(
                update_fields=["state", "updated_by", "ready_at", "updated_at"]
            )
            continue
        AgentToolStatus.objects.create(
            agent_id=agent_id,
            tool=tool,
            state=state,
            updated_by_id=setup.updated_by_id,
            ready_at=setup.updated_at if state == "ready" else None,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("onboarding_tools", "0003_agenttoolstatus_invitation_sent_at_and_more"),
        ("user", "0032_useronboardingcase_office_confirmation_version_and_more"),
    ]

    operations = [
        migrations.RunPython(
            migrate_legacy_tool_setups,
            migrations.RunPython.noop,
        ),
    ]
