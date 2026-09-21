"""Privacy-safe operational measures for the first-login onboarding journey.

Every measure is an aggregate derived from the tables that already own the
fact — the onboarding case, tool lifecycle, training progress, the composed
journey, and the audit log. Nothing here adds tracking, stores a new event, or
returns a name, email, profile value, free-text note, or exception text. The
scoped ``onboardingJourneyHealth`` report and the ``onboarding_health``
management command both call :func:`journey_health`.

View-level rejections (stale tokens, validation, storage outages) never reach a
table, so they are counted from logs instead: :func:`record_onboarding_error`
writes one ``onboarding_error code=<code>`` line with a stable code and no
request data.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from statistics import median

from django.db.models import Count, QuerySet

from apps.audit.models import AuditEvent
from apps.onboarding_tools.models import AgentToolStatus
from apps.training.models import TrainingProgress
from apps.training.taxonomy import CONTENT_TYPE_TOOL_ONBOARDING
from apps.user.models import User, UserOnboardingCase
from apps.user.services.onboarding_state import (
    ContractJourneyStatus,
    HandoffDeliveryState,
    JourneyStep,
    build_onboarding_states,
)

logger = logging.getLogger(__name__)


class OnboardingErrorCode(StrEnum):
    """Stable codes for rejected onboarding requests; safe to aggregate on."""

    STALE_ONBOARDING_VERSION = "stale_onboarding_version"
    STALE_PROFILE_SECTION = "stale_profile_section"
    PROFILE_INVALID = "profile_invalid"
    PROTECTED_FIELD_REJECTED = "protected_field_rejected"
    HEADSHOT_INVALID = "headshot_invalid"
    HEADSHOT_STORAGE_UNAVAILABLE = "headshot_storage_unavailable"
    ADMIN_ACTION_STALE = "admin_action_stale"
    ADMIN_ACTION_INVALID = "admin_action_invalid"


def record_onboarding_error(code: OnboardingErrorCode) -> None:
    """Count one rejected request by code. Never pass request data here."""
    logger.warning("onboarding_error code=%s", code.value)


#: Audit actions that record an onboarding failure. Each is already written by
#: its owning service; the action name is the stable error code.
FAILURE_AUDIT_ACTIONS = ("user.onboarding.office_handoff_unavailable",)

#: Blocker keys that mean an agent is waiting on a missing contact or a source
#: that could not answer, rather than on a person doing their step.
SOURCE_BLOCKER_KEYS = frozenset(
    {
        "office_handoff_failed",
        "contract_unavailable",
        "training_unavailable",
        "tools_unavailable",
    }
)


@dataclass(frozen=True)
class ToolTiming:
    tool: str
    invitations_sent: int
    ready: int
    median_hours_to_invitation: float | None
    median_hours_to_ready: float | None
    guides_opened: int
    guides_completed: int


@dataclass(frozen=True)
class JourneyHealth:
    """Aggregates only. Counters are keyed by stable enum values."""

    population: int
    journeys_started: int
    required_setup_completed: int
    activation_completed: int
    median_hours_to_required_setup: float | None
    current_steps: dict[str, int]
    handoff_states: dict[str, int]
    handoff_delivery: dict[str, int]
    contract_states: dict[str, int]
    blockers: dict[str, int]
    agents_blocked_by_source: int
    failures: dict[str, int]
    tools: tuple[ToolTiming, ...]
    as_of: datetime


def _hours(later: datetime | None, earlier: datetime | None) -> float | None:
    if later is None or earlier is None or later < earlier:
        return None
    return (later - earlier).total_seconds() / 3600


def _median(values: Iterable[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return round(median(present), 1) if present else None


def _ordered(counter: Counter[str], order: Iterable[str]) -> dict[str, int]:
    """Every known value, zero-filled, so an empty bucket still reads as zero."""
    known = {value: counter.get(value, 0) for value in order}
    extra = {key: count for key, count in sorted(counter.items()) if key not in known}
    return {**known, **extra}


def journey_health(population: QuerySet[User], *, now: datetime) -> JourneyHealth:
    """Aggregate the journey over an already scoped population.

    The caller owns scope: pass ``new_agent_queryset(actor)`` for a scoped
    viewer, or the unscoped new-agent filter for an operator. Staff and
    superusers never enter the Agent journey, so they are excluded here too.
    Query cost is fixed: the composer's bulk adapters plus three aggregate
    queries, independent of population size.
    """
    users = list(
        population.filter(is_staff=False, is_superuser=False)
        .select_related("office", "office__region", "onboarding_case")
        .prefetch_related("onboarding_case__tasks")
    )
    states = build_onboarding_states(users)
    user_ids = [user.pk for user in users]

    released_at: dict[int, datetime] = {}
    for state in states:
        case: UserOnboardingCase | None = state.case
        if case is not None and case.required_setup_completed_at is not None:
            released_at[state.user.pk] = case.required_setup_completed_at

    # Median time to required setup covers only journeys that began in the
    # hub. A legacy account backfilled as complete has no meaningful duration.
    setup_hours = [
        _hours(released_at.get(user.pk), user.date_joined)
        for user in users
        if (
            user.pk in released_at
            # Migration 0003 marked pre-onboarding accounts complete without a
            # completion timestamp. Migration 0031 later used ``date_joined``
            # for their compatibility checkpoint, which is not a measured
            # journey duration and must not contribute a synthetic zero.
            and user.profile_completed_at is not None
            and released_at[user.pk] >= user.date_joined
        )
    ]

    blockers: Counter[str] = Counter()
    source_blocked = 0
    for state in states:
        keys = {blocker["key"] for blocker in state.journey.blockers}
        blockers.update(keys)
        source_blocked += bool(keys & SOURCE_BLOCKER_KEYS)

    tool_rows = AgentToolStatus.objects.filter(agent_id__in=user_ids).values_list(
        "agent_id", "tool__slug", "invitation_sent_at", "ready_at"
    )
    invitation_hours: dict[str, list[float | None]] = {}
    ready_hours: dict[str, list[float | None]] = {}
    sent: Counter[str] = Counter()
    ready: Counter[str] = Counter()
    for agent_id, slug, invitation_sent_at, ready_at in tool_rows:
        start = released_at.get(agent_id)
        if invitation_sent_at is not None:
            sent[slug] += 1
            invitation_hours.setdefault(slug, []).append(
                _hours(invitation_sent_at, start)
            )
        if ready_at is not None:
            ready[slug] += 1
            ready_hours.setdefault(slug, []).append(_hours(ready_at, start))

    guides = (
        TrainingProgress.objects.filter(
            user_id__in=user_ids,
            content__content_type=CONTENT_TYPE_TOOL_ONBOARDING,
            started_at__isnull=False,
        )
        .values_list("content__tool_code", "user_id", "completed_at")
        .distinct()
    )
    opened: dict[str, set[int]] = {}
    completed: dict[str, set[int]] = {}
    for tool_code, user_id, completed_at in guides:
        opened.setdefault(tool_code, set()).add(user_id)
        if completed_at is not None:
            completed.setdefault(tool_code, set()).add(user_id)

    tool_keys = sorted(
        {item.key for state in states for item in state.journey.tools.items}
        | set(sent)
        | set(opened)
    )
    tools = tuple(
        ToolTiming(
            tool=key,
            invitations_sent=sent.get(key, 0),
            ready=ready.get(key, 0),
            median_hours_to_invitation=_median(invitation_hours.get(key, ())),
            median_hours_to_ready=_median(ready_hours.get(key, ())),
            guides_opened=len(opened.get(key, ())),
            guides_completed=len(completed.get(key, ())),
        )
        for key in tool_keys
    )

    failures = Counter(
        dict(
            AuditEvent.objects.filter(
                action__in=FAILURE_AUDIT_ACTIONS,
                target_type=UserOnboardingCase._meta.label_lower,
                target_id__in=[str(pk) for pk in user_ids],
            )
            .values_list("action")
            .annotate(total=Count("id"))
            .values_list("action", "total")
        )
    )

    return JourneyHealth(
        population=len(users),
        journeys_started=sum(user.last_login is not None for user in users),
        required_setup_completed=len(released_at),
        activation_completed=sum(state.journey.activation_complete for state in states),
        median_hours_to_required_setup=_median(setup_hours),
        current_steps=_ordered(
            Counter(str(state.journey.current_step) for state in states),
            [str(step) for step in JourneyStep],
        ),
        handoff_states=_ordered(
            Counter(
                str(state.case.office_handoff_state)
                for state in states
                if state.user.pk in released_at and state.case is not None
            ),
            [str(value) for value in UserOnboardingCase.OfficeHandoffState],
        ),
        handoff_delivery=_ordered(
            Counter(
                str(state.journey.office_handoff_delivery_state)
                for state in states
                if state.user.pk in released_at
            ),
            [str(value) for value in HandoffDeliveryState],
        ),
        contract_states=_ordered(
            Counter(str(state.journey.contract_status) for state in states),
            [str(value) for value in ContractJourneyStatus],
        ),
        blockers=dict(sorted(blockers.items())),
        agents_blocked_by_source=source_blocked,
        failures=_ordered(failures, FAILURE_AUDIT_ACTIONS),
        tools=tools,
        as_of=now,
    )
