"""Shared action-item contract.

Domain modules emit :class:`ActionItem` rows. The dashboard composer merges,
deduplicates, and orders them — it does not own completion state or invent
records. Completion is always derived from the source record: a provider that
would emit a completed, cancelled, future-not-actionable, or out-of-scope item
must omit it instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


class ActionType:
    PROFILE = "profile"
    CONTRACT = "contract"
    TRANSACTION = "transaction"
    DOCUMENT = "document"
    CHECKLIST = "checklist"
    TRAINING = "training"
    LEAD = "lead"
    COMMISSION = "commission"
    COMPLIANCE = "compliance"
    INVENTORY = "inventory"


ACTION_TYPES: frozenset[str] = frozenset(
    {
        ActionType.PROFILE,
        ActionType.CONTRACT,
        ActionType.TRANSACTION,
        ActionType.DOCUMENT,
        ActionType.CHECKLIST,
        ActionType.TRAINING,
        ActionType.LEAD,
        ActionType.COMMISSION,
        ActionType.COMPLIANCE,
        ActionType.INVENTORY,
    }
)


class ActionPriority:
    """Lower number sorts first after the overdue flag."""

    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4


PRIORITY_LABELS: dict[int, str] = {
    ActionPriority.CRITICAL: "Critical",
    ActionPriority.HIGH: "High priority",
    ActionPriority.NORMAL: "Normal",
    ActionPriority.LOW: "Low priority",
}

PRIORITY_KEYS: dict[int, str] = {
    ActionPriority.CRITICAL: "critical",
    ActionPriority.HIGH: "high",
    ActionPriority.NORMAL: "normal",
    ActionPriority.LOW: "low",
}


class ActionState:
    """Only open items cross the wire.

    There is no dashboard-owned completion flag. Dismissing a row on the
    dashboard must never mark a legal, compliance, or other source-domain item
    complete — that truth lives on the source record alone.
    """

    OPEN = "open"


@dataclass(frozen=True)
class ActionItem:
    """One actionable row from a domain source.

    ``id`` is stable across requests for the same required action.
    ``dedupe_key`` collapses duplicate signals (e.g. the same unsigned
    contract surfacing from two providers) to a single row.
    """

    id: str
    dedupe_key: str
    title: str
    type: str
    priority: int
    due_at: datetime | None
    source_module: str
    source_record_type: str
    source_record_id: str
    context: str
    cta_label: str
    cta_href: str
    assignee_id: int
    state: str = ActionState.OPEN

    def __post_init__(self) -> None:
        if self.type not in ACTION_TYPES:
            raise ValueError(f"Unknown action type: {self.type!r}")
        if self.priority not in PRIORITY_LABELS:
            raise ValueError(f"Unknown action priority: {self.priority!r}")
        if self.state != ActionState.OPEN:
            raise ValueError(
                "Only open action items may be emitted; completion is "
                f"derived from the source record, got state={self.state!r}"
            )
        if not self.id or not self.dedupe_key:
            raise ValueError("Action items need a stable id and dedupe_key")
        if not self.cta_href or not self.cta_label:
            raise ValueError("Action items need a CTA label and destination")


@dataclass(frozen=True)
class ActionSourceContext:
    """Everything a source collector may read.

    Never accept office, owner, or record ids from the client. The signed-in
    user and their pre-resolved effective access are the only identity inputs.
    """

    user: Any  # apps.user.models.User — avoid circular import at module load
    access: Any  # EffectiveAccess
    now: datetime
