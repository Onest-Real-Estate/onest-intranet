"""Resolving an agent's tool checklist, and moving one row on it.

Two reads and one write:

* :func:`checklist_for` answers "what does this agent need, and where are they
  with each one" — the catalog filtered to their office, joined to whatever
  progress exists.
* :func:`readiness_for` answers the same question in one line, for a manager
  looking at a list of people.
* :func:`set_state` is the only writer, and it authorizes against the *stored*
  agent rather than a posted id.

Rows are created lazily. A tool with no status row is simply "not started", so
adding a tool to the catalog costs nothing and does not require writing a row
for every agent in the brokerage.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.service import actor_from_user, log_on_commit, target_from_instance
from apps.onboarding_tools.models import (
    COMPLETE_STATES,
    PROVISIONED_ONLY_STATES,
    SETTLED_STATES,
    STATE_ORDER,
    AgentToolStatus,
    OnboardingTool,
    Provisioning,
    ToolState,
)
from apps.user.models import Office

#: Managing somebody else's checklist is the existing onboarding grant. There is
#: deliberately no new permission: the people who run onboarding are the people
#: who already hold this, and a second grant would be one more thing to forget
#: when somebody joins the IT team.
MANAGE_PERMISSION = "web.manage_new_agent_onboarding"


class ToolWorkspaceAction(StrEnum):
    """Stable commands exposed to administrative onboarding surfaces."""

    MARK_INVITATION_SENT = "mark_invitation_sent"
    REVOKE_INVITATION = "revoke_invitation"
    MARK_READY = "mark_ready"
    MARK_BLOCKED = "mark_blocked"
    RETRY_NOTIFICATION = "retry_notification"


class ToolWorkspaceGroup(StrEnum):
    WAITING = "waiting"
    INVITATION_SENT = "invitation_sent"
    READY = "ready"
    BLOCKED = "blocked"
    NOT_APPLICABLE = "not_applicable"


class ToolDeliveryState(StrEnum):
    NOT_RECORDED = "not_recorded"
    RECORDED = "recorded"
    QUEUED = "queued"
    SENT = "sent"
    RETRYABLE = "retryable"
    FAILED = "failed"
    SUPPRESSED = "suppressed"


INVITATION_EVENT = "onboarding_tool.state_changed"


def invitation_dedupe_key(
    *, agent_id: int, onboarding_version: int, tool_slug: str
) -> str:
    """One agent notice per onboarding cycle, tool, and invitation transition."""
    return (
        f"tool-invitation:agent:{agent_id}:version:{onboarding_version}:"
        f"tool:{tool_slug}:transition:{ToolState.INVITATION_SENT}"
    )


@dataclass(frozen=True)
class ToolProgress:
    """One catalog row joined to this agent's state on it."""

    tool: OnboardingTool
    state: str
    note: str
    updated_at: Any
    invitation_sent_at: Any = None
    #: The agent's own "I have this". Never counted toward readiness.
    agent_confirmed_at: Any = None

    @property
    def is_complete(self) -> bool:
        return self.state in COMPLETE_STATES


@dataclass(frozen=True)
class Readiness:
    """How far one agent has got, in one line."""

    ready: int
    total: int

    @property
    def percent(self) -> int:
        # Zero tools is 100% done, not a division error: an agent with no
        # applicable tools is not blocked on anything.
        return 100 if self.total == 0 else round(self.ready * 100 / self.total)

    @property
    def is_complete(self) -> bool:
        return self.ready >= self.total


def checklist_for(agent) -> list[ToolProgress]:
    """Every tool this agent needs, in catalog order, with their state.

    One query for the catalog and one for the statuses — never one per tool,
    which is what a naive template loop would produce for two dozen rows.
    """
    tools = list(
        OnboardingTool.objects.for_office(getattr(agent, "office", None)).order_by(
            "group", "sort_order", "name"
        )
    )
    if not tools:
        return []

    states = {
        row.tool_id: row
        for row in AgentToolStatus.objects.filter(agent=agent, tool__in=tools).only(
            "tool_id",
            "state",
            "note",
            "updated_at",
            "invitation_sent_at",
            "agent_confirmed_at",
        )
    }
    progress: list[ToolProgress] = []
    for tool in tools:
        row = states.get(tool.pk)
        progress.append(
            ToolProgress(
                tool=tool,
                state=row.state if row else ToolState.NOT_STARTED,
                note=row.note if row else "",
                updated_at=row.updated_at if row else None,
                invitation_sent_at=row.invitation_sent_at if row else None,
                agent_confirmed_at=row.agent_confirmed_at if row else None,
            )
        )
    return progress


def readiness_for(agent) -> Readiness:
    """The one-line figure, counting only tools the agent is expected to have.

    An optional tool left alone must not make somebody read as incomplete —
    that is what ``is_required`` is for, and counting it would make the figure
    unreachable.
    """
    rows = [item for item in checklist_for(agent) if item.tool.is_required]
    return Readiness(ready=sum(1 for item in rows if item.is_complete), total=len(rows))


def bulk_agent_onboarding_states(users):
    """Resolve every applicable tool for many agents in four bounded queries."""
    from apps.user.services.onboarding_state import (
        JourneyToolState,
        MilestoneStatus,
        ToolInvitationStatus,
        ToolOnboardingState,
        ToolSourceStatus,
    )

    if not users:
        return {}
    tools = list(
        OnboardingTool.objects.live()
        .prefetch_related("office_audiences")
        .order_by("group", "sort_order", "name")
    )
    parent_by_id = dict(Office.objects.values_list("pk", "parent_id"))
    statuses = {
        (row.agent_id, row.tool_id): row
        for row in AgentToolStatus.objects.filter(
            agent_id__in=[user.pk for user in users],
            tool_id__in=[tool.pk for tool in tools],
        ).select_related("updated_by")
    }
    state_labels = dict(ToolState.choices)
    provisioning_labels = dict(Provisioning.choices)

    def office_chain(office_id):
        chain = set()
        current = office_id
        while current and current not in chain:
            chain.add(current)
            current = parent_by_id.get(current)
        return chain

    result = {}
    for user in users:
        chain = office_chain(user.office_id)
        items = []
        for tool in tools:
            audiences = list(tool.office_audiences.all())
            applies = tool.company_wide or any(
                audience.office_id == user.office_id
                or (audience.include_descendants and audience.office_id in chain)
                for audience in audiences
            )
            if not applies:
                continue
            row = statuses.get((user.pk, tool.pk))
            state = ToolState(row.state if row else ToolState.NOT_STARTED)
            if state in COMPLETE_STATES:
                status = MilestoneStatus.COMPLETE
            elif state == ToolState.BLOCKED:
                status = MilestoneStatus.BLOCKED
            else:
                status = MilestoneStatus.PENDING
            invitation_sent_at = row.invitation_sent_at if row else None
            if tool.provisioning == Provisioning.SELF_SERVE:
                invitation = ToolInvitationStatus.NOT_APPLICABLE
                invitation_label = "You set this one up yourself"
            elif invitation_sent_at is not None:
                invitation = ToolInvitationStatus.SENT
                invitation_label = "Invitation sent"
            else:
                invitation = ToolInvitationStatus.PENDING
                invitation_label = "Waiting on your office"
            items.append(
                JourneyToolState(
                    key=tool.slug,
                    label=tool.name,
                    description=tool.description,
                    provisioning=tool.provisioning,
                    provisioning_label=str(
                        provisioning_labels.get(tool.provisioning, tool.provisioning)
                    ),
                    self_service=tool.is_self_serve,
                    required=tool.is_required,
                    state=str(state),
                    state_label=str(state_labels.get(state, state)),
                    status=status,
                    invitation_status=invitation,
                    invitation_label=invitation_label,
                    complete=state in COMPLETE_STATES,
                    updated_at=row.updated_at if row else None,
                    invitation_sent_at=invitation_sent_at,
                    updated_by_label=(
                        str(row.updated_by) if row and row.updated_by else ""
                    ),
                    applicable=state != ToolState.NOT_APPLICABLE,
                    help_url=tool.help_url,
                    request_path=tool.request_path,
                    contact_label=tool.contact_label,
                )
            )
        result[user.pk] = ToolOnboardingState(
            source_status=ToolSourceStatus.AVAILABLE,
            items=tuple(items),
        )
    return result


def can_manage(actor, agent) -> bool:
    """Whether this actor may move somebody else's checklist.

    Self-management is refused on purpose, matching the New Agent List: an
    agent marking their own Office 365 "ready" tells nobody anything, and the
    figure stops meaning "IT confirmed this works".
    """
    if getattr(actor, "pk", None) == getattr(agent, "pk", None):
        return False
    if getattr(actor, "is_superuser", False):
        return True
    # The project's effective union, not ``has_perm``: onboarding managers hold
    # this through a scoped role assignment, and the New Agent List authorizes
    # the same way. Two different answers to "may this person manage tools"
    # is how one surface silently refuses what the other allows.
    from apps.user.services.role_assignments import has_effective_permission

    return has_effective_permission(actor, MANAGE_PERMISSION)


def invitation_delivery_states(
    *, agent, onboarding_version: int, tool_slugs: list[str]
) -> dict[str, dict[str, Any]]:
    """Read every current invitation notice in two bounded notification queries."""
    from apps.notifications.models import Notification, NotificationEmail

    keys = {
        slug: invitation_dedupe_key(
            agent_id=agent.pk,
            onboarding_version=onboarding_version,
            tool_slug=slug,
        )
        for slug in tool_slugs
    }
    rows = (
        Notification.objects.filter(
            recipient=agent,
            event_key=INVITATION_EVENT,
            dedupe_key__in=keys.values(),
        )
        .prefetch_related("deliveries")
        .order_by("pk")
    )
    by_key = {row.dedupe_key: row for row in rows}
    result: dict[str, dict[str, Any]] = {}
    for slug, key in keys.items():
        notification = by_key.get(key)
        if notification is None:
            result[slug] = {
                "state": ToolDeliveryState.NOT_RECORDED,
                "label": "Agent notice not recorded",
                "channels": (),
                "retryable": False,
            }
            continue
        deliveries = tuple(
            {
                "channel": delivery.channel,
                "state": delivery.status,
                "label": str(NotificationEmail.Status(delivery.status).label),
            }
            for delivery in notification.deliveries.all()  # ty: ignore[unresolved-attribute]
        )
        statuses = {delivery["state"] for delivery in deliveries}
        if NotificationEmail.Status.FAILED in statuses:
            state = ToolDeliveryState.RETRYABLE
            label = "Outbound notice will retry"
        elif NotificationEmail.Status.DEAD in statuses:
            state = ToolDeliveryState.FAILED
            label = "Outbound notice failed"
        elif NotificationEmail.Status.PENDING in statuses or (
            NotificationEmail.Status.SENDING in statuses
        ):
            state = ToolDeliveryState.QUEUED
            label = "Outbound notice queued"
        elif NotificationEmail.Status.SENT in statuses:
            state = ToolDeliveryState.SENT
            label = "Agent notice sent"
        elif NotificationEmail.Status.SUPPRESSED in statuses:
            state = ToolDeliveryState.SUPPRESSED
            label = "Outbound notice suppressed"
        else:
            state = ToolDeliveryState.RECORDED
            label = "Agent notice recorded in the Hub"
        result[slug] = {
            "state": state,
            "label": label,
            "channels": deliveries,
            "retryable": state
            in {ToolDeliveryState.RETRYABLE, ToolDeliveryState.FAILED},
        }
    return result


def workspace_capabilities(
    *,
    editable: bool,
    tool_slug: str,
    provisioning: str,
    state: str,
    required_setup_complete: bool,
    delivery: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Return source-owned commands; callers render these without vendor branches."""
    unavailable_reason = ""
    if not editable:
        unavailable_reason = "You do not have permission to manage this tool."
    elif not required_setup_complete:
        unavailable_reason = (
            "Wait until the agent completes their profile and confirms their office."
        )

    def action(
        code: ToolWorkspaceAction,
        label: str,
        *,
        requires_reason: bool = False,
    ) -> dict[str, Any]:
        return {
            "code": str(code),
            "label": label,
            "tool": tool_slug,
            "requiresReason": requires_reason,
            "enabled": not unavailable_reason,
            "unavailableReason": unavailable_reason,
        }

    actions: list[dict[str, Any]] = []
    provisioned = provisioning != Provisioning.SELF_SERVE
    invitation_recorded = state in {
        ToolState.INVITATION_SENT,
        ToolState.IN_PROGRESS,
        ToolState.READY,
    }
    leaving_settled_state = state in SETTLED_STATES
    if provisioned and not invitation_recorded:
        actions.append(
            action(
                ToolWorkspaceAction.MARK_INVITATION_SENT,
                "Mark invitation sent",
                requires_reason=leaving_settled_state,
            )
        )
    elif provisioned and invitation_recorded:
        actions.append(
            action(
                ToolWorkspaceAction.REVOKE_INVITATION,
                "Correct invitation record",
                requires_reason=True,
            )
        )
    if state != ToolState.READY:
        actions.append(
            action(
                ToolWorkspaceAction.MARK_READY,
                "Mark ready",
                requires_reason=leaving_settled_state,
            )
        )
    if state not in {ToolState.BLOCKED, ToolState.NOT_APPLICABLE}:
        actions.append(
            action(
                ToolWorkspaceAction.MARK_BLOCKED,
                "Mark blocked",
                requires_reason=True,
            )
        )
    if delivery.get("retryable"):
        actions.insert(
            0,
            action(
                ToolWorkspaceAction.RETRY_NOTIFICATION,
                "Retry agent notice",
            ),
        )
    return tuple(actions)


def workspace_group(*, state: str, invitation_sent_at) -> ToolWorkspaceGroup:
    if state == ToolState.NOT_APPLICABLE:
        return ToolWorkspaceGroup.NOT_APPLICABLE
    if state == ToolState.BLOCKED:
        return ToolWorkspaceGroup.BLOCKED
    if state == ToolState.READY:
        return ToolWorkspaceGroup.READY
    if invitation_sent_at is not None or state in {
        ToolState.INVITATION_SENT,
        ToolState.IN_PROGRESS,
    }:
        return ToolWorkspaceGroup.INVITATION_SENT
    return ToolWorkspaceGroup.WAITING


@transaction.atomic
def perform_workspace_action(
    *, actor, agent, tool: OnboardingTool, action: str, reason: str = ""
):
    """Translate one reviewed command into the lifecycle's single state writer."""
    try:
        command = ToolWorkspaceAction(action)
    except ValueError as exc:
        raise ValidationError({"action": ["Choose an available tool action."]}) from exc
    if command == ToolWorkspaceAction.RETRY_NOTIFICATION:
        return retry_invitation_notice(
            actor=actor,
            agent=agent,
            tool=tool,
            onboarding_version=agent.onboarding_version,
        )
    target = {
        ToolWorkspaceAction.MARK_INVITATION_SENT: ToolState.INVITATION_SENT,
        ToolWorkspaceAction.REVOKE_INVITATION: ToolState.REQUESTED,
        ToolWorkspaceAction.MARK_READY: ToolState.READY,
        ToolWorkspaceAction.MARK_BLOCKED: ToolState.BLOCKED,
    }[command]
    row = AgentToolStatus.objects.filter(agent=agent, tool=tool).first()
    current = ToolState(row.state if row else ToolState.NOT_STARTED)
    if current == target:
        # An exact repeated command is a source-level no-op. The workspace
        # version still protects a different concurrent transition.
        return row or AgentToolStatus(agent=agent, tool=tool, state=current)
    invitation_recorded = current in {
        ToolState.INVITATION_SENT,
        ToolState.IN_PROGRESS,
        ToolState.READY,
    }
    allowed = {
        ToolWorkspaceAction.MARK_INVITATION_SENT: (
            tool.provisioning != Provisioning.SELF_SERVE and not invitation_recorded
        ),
        ToolWorkspaceAction.REVOKE_INVITATION: (
            tool.provisioning != Provisioning.SELF_SERVE and invitation_recorded
        ),
        ToolWorkspaceAction.MARK_READY: current != ToolState.READY,
        ToolWorkspaceAction.MARK_BLOCKED: current
        not in {ToolState.BLOCKED, ToolState.NOT_APPLICABLE},
    }[command]
    if not allowed:
        raise ValidationError(
            {"action": ["That action is not available for the tool's current state."]}
        )
    try:
        return set_state(actor=actor, agent=agent, tool=tool, state=target, note=reason)
    except ValidationError as exc:
        # ``note`` is the source model's field; the workspace intentionally
        # exposes the narrower, safer command name reason instead.
        if "note" not in exc.message_dict:
            raise
        raise ValidationError({"reason": exc.message_dict["note"]}) from exc


def retry_invitation_notice(
    *, actor, agent, tool: OnboardingTool, onboarding_version: int
) -> int:
    """Requeue only failed deliveries for this exact agent/tool/cycle notice."""
    if not can_manage(actor, agent):
        raise PermissionDenied("You cannot retry this person's tool notice.")
    from apps.notifications.delivery import retry_failed_delivery
    from apps.notifications.models import NotificationEmail

    key = invitation_dedupe_key(
        agent_id=agent.pk,
        onboarding_version=onboarding_version,
        tool_slug=tool.slug,
    )
    rows = list(
        NotificationEmail.objects.select_related("notification").filter(
            notification__recipient=agent,
            notification__event_key=INVITATION_EVENT,
            notification__dedupe_key=key,
            status__in=(
                NotificationEmail.Status.FAILED,
                NotificationEmail.Status.DEAD,
            ),
        )
    )
    if not rows:
        raise ValidationError(
            {"action": ["There is no failed invitation notice to retry."]}
        )
    for row in rows:
        retry_failed_delivery(actor=actor, delivery=row)
    return len(rows)


def state_rank(state: str) -> int:
    """Position on the normal setup ladder; ``-1`` for the settled states."""
    try:
        return STATE_ORDER.index(state)
    except ValueError:
        return -1


def validate_transition(
    *, tool: OnboardingTool, current: str, target: str, reason: str
) -> None:
    """Refuse states a tool cannot hold, and corrections without a reason.

    Skipping *forward* is ordinary — a self-serve tool goes straight to ready.
    Moving back down the ladder, or out of a settled state, is a correction:
    the person who marked an invitation sent by mistake has to say so, because
    the agent was told it was sent.
    """
    if target not in ToolState.values:
        raise ValidationError({"state": ["Unknown state."]})
    if (
        target in PROVISIONED_ONLY_STATES
        and tool.provisioning == Provisioning.SELF_SERVE
    ):
        raise ValidationError(
            {
                "state": [
                    f"{tool.name} is one the agent sets up, so there is no "
                    "invitation for anybody to send."
                ]
            }
        )
    if current == target:
        return
    target_rank = state_rank(target)
    backward = target_rank >= 0 and state_rank(current) > target_rank
    revoking = current in SETTLED_STATES and target not in SETTLED_STATES
    if (backward or revoking) and not reason:
        raise ValidationError(
            {
                "note": [
                    "Say why this is moving back. Corrections are recorded "
                    "against the person who made them."
                ]
            }
        )


@transaction.atomic
def set_state(*, actor, agent, tool: OnboardingTool, state: str, note: str = ""):
    """Move one agent's state on one tool. The only writer.

    Authorizes against the stored agent, creates the row lazily, validates the
    move, and keeps every timestamp the database constraints require in step:
    ``ready_at`` with ready, and the invitation provenance with
    ``invitation_sent``.
    """
    if not can_manage(actor, agent):
        raise PermissionDenied("You cannot change this person's tool setup.")

    row, _created = AgentToolStatus.objects.select_for_update(
        of=("self",)
    ).get_or_create(agent=agent, tool=tool, defaults={"updated_by": actor})
    reason = note.strip()[:300]
    validate_transition(tool=tool, current=row.state, target=state, reason=reason)
    if row.state == state and row.note == reason:
        # Idempotent: a double-clicked control is not an event worth auditing
        # twice, and re-sending is an explicit act, not a repeated submit.
        return row

    before = row.state
    now = timezone.now()
    row.state = state
    row.note = reason
    row.updated_by = actor
    row.ready_at = now if state == ToolState.READY else None
    if state in {ToolState.REQUESTED, ToolState.INVITATION_SENT}:
        row.requested_at = row.requested_at or now
    if state == ToolState.INVITATION_SENT:
        # A re-send records the latest one: "when was I invited" is the
        # question the agent and training are actually asking.
        row.invitation_sent_at = now
        row.invitation_sent_by = actor
    elif 0 <= state_rank(state) < state_rank(ToolState.INVITATION_SENT):
        # Moved back behind the invitation, so the provenance is no longer
        # true. Leave it in place for states that come after it.
        row.invitation_sent_at = None
        row.invitation_sent_by = None
    row.save(
        update_fields=[
            "state",
            "note",
            "updated_by",
            "ready_at",
            "requested_at",
            "invitation_sent_at",
            "invitation_sent_by",
            "updated_at",
        ]
    )

    log_on_commit(
        action="onboarding_tool.state_changed",
        actor=actor_from_user(actor),
        target=target_from_instance(row, label=f"{agent} / {tool.name}"),
        before={"state": before},
        after={"state": state},
        metadata={
            "agent_id": agent.pk,
            "tool": tool.slug,
            "from": before,
            "to": state,
        },
    )
    _publish_state_change(actor=actor, agent=agent, tool=tool, before=before, row=row)
    return row


@transaction.atomic
def set_agent_confirmation(*, agent, slug: str, confirmed: bool) -> AgentToolStatus:
    """Record or withdraw the agent's own "I have this" on one tool.

    Only ever the signed-in agent's own row: there is no ``actor`` because the
    agent *is* the actor, and nobody may claim a tool on somebody else's
    behalf. The tool is resolved against the agent's applicable catalog, so a
    slug for another office's MLS is refused rather than silently recorded.

    ``state`` is deliberately untouched. Readiness still means "somebody at
    oNEST confirmed this", which is why self-management stays refused there.
    """
    tool = (
        OnboardingTool.objects.for_office(getattr(agent, "office", None))
        .filter(slug=slug)
        .first()
    )
    if tool is None:
        raise ValidationError({"tool": ["That tool is not on your checklist."]})

    row, _created = AgentToolStatus.objects.select_for_update(
        of=("self",)
    ).get_or_create(agent=agent, tool=tool)
    if bool(row.agent_confirmed_at) == confirmed:
        # Idempotent: a double-clicked box is not two events.
        return row

    before = row.agent_confirmed_at
    row.agent_confirmed_at = timezone.now() if confirmed else None
    row.save(update_fields=["agent_confirmed_at"])
    log_on_commit(
        action="onboarding_tool.agent_confirmed"
        if confirmed
        else "onboarding_tool.agent_unconfirmed",
        actor=actor_from_user(agent),
        target=target_from_instance(row, label=f"{agent} / {tool.name}"),
        before={"agentConfirmed": before is not None},
        after={"agentConfirmed": confirmed},
        metadata={"agent_id": agent.pk, "tool": tool.slug},
    )
    return row


def _publish_state_change(*, actor, agent, tool: OnboardingTool, before: str, row):
    """Durable event for downstream consumers: identifiers and enums only.

    The operational note never travels. It is free text a person typed about
    somebody's account, and no consumer needs it to react to a state change.
    """
    from apps.audit.events import publish

    publish(
        "onboarding_tool.state_changed",
        actor_id=str(getattr(actor, "pk", "")),
        subject=f"user:{agent.pk}",
        payload={
            "tool": tool.slug,
            "tool_name": tool.name,
            "agent_id": agent.pk,
            "office_id": getattr(agent, "office_id", None),
            "onboarding_version": agent.onboarding_version,
            "from": str(before),
            "to": str(row.state),
            "actor_id": getattr(actor, "pk", None),
            "invitation_sent_at": (
                row.invitation_sent_at.isoformat() if row.invitation_sent_at else None
            ),
            "ready_at": row.ready_at.isoformat() if row.ready_at else None,
        },
    )


# --------------------------------------------------------------------------- #
# Catalog administration
# --------------------------------------------------------------------------- #

#: Editing the catalog is brokerage-wide configuration and a separate grant
#: from moving one agent's checklist: a branch manager runs onboarding for
#: their branch, and should not be able to redefine what every office needs.
CATALOG_PERMISSION = "web.manage_onboarding_tools"


def can_manage_catalog(actor) -> bool:
    return bool(
        getattr(actor, "is_superuser", False) or actor.has_perm(CATALOG_PERMISSION)
    )


def _require_catalog(actor) -> None:
    if not can_manage_catalog(actor):
        raise PermissionDenied("You cannot change the tool catalog.")


@transaction.atomic
def save_tool(*, actor, form, instance=None):
    """Create or update one catalog row from a validated form.

    The audience rows are replaced wholesale rather than diffed: the form
    submits the complete intended set, and reconciling a partial edit against
    what was there is how an office quietly survives being unticked.
    """
    from apps.onboarding_tools.models import OnboardingToolOfficeAudience

    _require_catalog(actor)

    tool = form.save(commit=False)
    tool.setup_steps = form.cleaned_data["setup_steps"]
    created = tool.pk is None
    tool.save()

    OnboardingToolOfficeAudience.objects.filter(tool=tool).delete()
    if not tool.company_wide:
        OnboardingToolOfficeAudience.objects.bulk_create(
            [
                OnboardingToolOfficeAudience(
                    tool=tool, office=office, include_descendants=True
                )
                for office in form.cleaned_data["offices"]
            ]
        )

    log_on_commit(
        action="onboarding_tool.created" if created else "onboarding_tool.updated",
        actor=actor_from_user(actor),
        target=target_from_instance(tool, label=tool.name),
        metadata={
            "slug": tool.slug,
            "group": tool.group,
            "companyWide": tool.company_wide,
            "active": tool.is_active,
        },
    )
    return tool


@transaction.atomic
def reorder_tools(*, actor, group: str, slugs: list[str]) -> int:
    """Set the display order within one group.

    Only rows already in that group are touched, so a slug from elsewhere in
    the catalog cannot be dragged into it by a crafted post. Returns how many
    rows moved.
    """
    _require_catalog(actor)

    from apps.onboarding_tools.models import OnboardingTool as Tool

    in_group = {
        tool.slug: tool
        for tool in Tool.objects.select_for_update(of=("self",)).filter(group=group)
    }
    moved = 0
    for position, slug in enumerate(slugs):
        tool = in_group.get(slug)
        if tool is None or tool.sort_order == position * 10:
            continue
        tool.sort_order = position * 10
        tool.save(update_fields=["sort_order", "updated_at"])
        moved += 1

    if moved:
        log_on_commit(
            action="onboarding_tool.reordered",
            actor=actor_from_user(actor),
            target=target_from_instance(
                next(iter(in_group.values())), label=f"{group} catalog"
            ),
            metadata={"group": group, "moved": moved},
        )
    return moved
