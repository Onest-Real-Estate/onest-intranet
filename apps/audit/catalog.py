"""Official ONEST domain-event catalog.

All events must be registered here before they can be published.  To add a
new event:

1. Add a ``registry.register(...)`` call with a unique name, version, the set
   of required payload keys, and a clear description.
2. Open a PR describing the schema contract so consumers can be updated.

Schema versioning
-----------------
- Additive changes (new *optional* keys) do not require a version bump.
- Breaking changes (removing / renaming required keys) require incrementing
  ``version`` and registering the new schema alongside the old one so that
  already-queued events with the old version are still valid.

Ownership
---------
Each comment names the Django app/service responsible for publishing.
"""

from apps.audit.events import registry

# ---------------------------------------------------------------------------
# user domain  (publisher: apps.user)
# ---------------------------------------------------------------------------

registry.register(
    name="user.onboarded",
    version=1,
    required_payload_keys={"user_id", "email", "office_id"},
    description=(
        "Emitted once when a user completes the onboarding form for the first time. "
        "office_id is null if the user did not select an office."
    ),
)

registry.register(
    name="user.account.state_changed",
    version=1,
    required_payload_keys={"user_id", "is_active"},
    description=(
        "A user account was disabled or reactivated by an administrator. "
        "Disabling also revokes every live session; the count is reported as "
        "sessions_revoked."
    ),
)

registry.register(
    name="user.onboarding.owner_assigned",
    version=1,
    required_payload_keys={"user_id", "owner_id"},
    description="Operational onboarding ownership changed for a user.",
)

registry.register(
    name="user.onboarding.task_changed",
    version=1,
    required_payload_keys={"user_id", "task_id", "status"},
    description="An operational onboarding task was created or resolved.",
)

registry.register(
    name="user.onboarding.tool_setup_changed",
    version=1,
    required_payload_keys={"user_id", "tool", "state"},
    description="An approved operational tool-setup state changed.",
)

registry.register(
    name="user.onboarding.notice_resent",
    version=1,
    required_payload_keys={"user_id", "source", "notice"},
    description="A source-owned onboarding notice resend was requested.",
)

# ---------------------------------------------------------------------------
# contract domain  (publisher: apps.contract.lifecycle / services)
# ---------------------------------------------------------------------------

registry.register(
    name="contract.created",
    version=1,
    required_payload_keys={"contract_id", "office_id", "agent_id"},
    description="Emitted when an agent creates a new contract draft.",
)

registry.register(
    name="contract.issued",
    version=1,
    required_payload_keys={
        "contract_id",
        "office_id",
        "agent_id",
        "status",
        "occurred_at",
    },
    description="Emitted when a ready contract is issued/sent to the agent.",
)

registry.register(
    name="contract.signed",
    version=1,
    required_payload_keys={"contract_id", "signer_id", "signed_at"},
    description="Emitted when all required parties have signed a contract.",
)

registry.register(
    name="contract.activated",
    version=1,
    required_payload_keys={
        "contract_id",
        "office_id",
        "agent_id",
        "status",
        "occurred_at",
    },
    description=(
        "Emitted when a signed contract becomes the governing active agreement."
    ),
)

registry.register(
    name="contract.superseded",
    version=1,
    required_payload_keys={
        "contract_id",
        "office_id",
        "agent_id",
        "status",
        "occurred_at",
    },
    description="Emitted when a contract is superseded by a replacement.",
)

registry.register(
    name="contract.terminated",
    version=1,
    required_payload_keys={
        "contract_id",
        "office_id",
        "agent_id",
        "status",
        "occurred_at",
    },
    description="Emitted when a contract is terminated.",
)

registry.register(
    name="contract.expired",
    version=1,
    required_payload_keys={
        "contract_id",
        "office_id",
        "agent_id",
        "status",
        "occurred_at",
    },
    description="Emitted when an active contract expires by policy date.",
)

registry.register(
    name="contract.pdf_ready",
    version=1,
    required_payload_keys={
        "contract_id",
        "office_id",
        "agent_id",
        "artifact_id",
        "checksum",
        "occurred_at",
    },
    description=(
        "Emitted once when the authoritative review PDF is stored for an "
        "issued contract. Idempotent retries must not emit a second event."
    ),
)

registry.register(
    name="contract.signed_pdf_ready",
    version=1,
    required_payload_keys={
        "contract_id",
        "office_id",
        "agent_id",
        "signature_id",
        "artifact_id",
        "checksum",
        "source_checksum",
        "occurred_at",
    },
    description=(
        "Emitted once when the authoritative final signed PDF (legal pages + "
        "certificate) is stored for a signature record. Idempotent retries "
        "must not emit a second event."
    ),
)

registry.register(
    name="contract.viewed",
    version=1,
    required_payload_keys={
        "contract_id",
        "office_id",
        "agent_id",
        "status",
        "occurred_at",
    },
    description="Emitted when the recipient first views an issued contract.",
)

registry.register(
    name="contract.generation_error",
    version=1,
    required_payload_keys={
        "contract_id",
        "office_id",
        "agent_id",
        "status",
        "occurred_at",
    },
    description=(
        "Emitted when PDF/finalization fails. Payload carries ids only — never "
        "party or commercial content."
    ),
)

registry.register(
    name="contract.signature_reminder",
    version=1,
    required_payload_keys={
        "contract_id",
        "office_id",
        "agent_id",
        "reminder_day",
        "occurred_at",
    },
    description=(
        "Emitted on an approved cadence while a contract remains signable. "
        "Beat tasks re-check status before publishing."
    ),
)

registry.register(
    name="contract.expiration_warning",
    version=1,
    required_payload_keys={
        "contract_id",
        "office_id",
        "agent_id",
        "warning_day",
        "occurred_at",
    },
    description=(
        "Emitted when an active contract is within an approved window of "
        "expires_on. Beat tasks re-check status before publishing."
    ),
)

# ---------------------------------------------------------------------------
# transaction domain  (publisher: apps.transaction — future)
# ---------------------------------------------------------------------------

registry.register(
    name="transaction.created",
    version=1,
    required_payload_keys={"transaction_id", "contract_id", "office_id"},
    description="Emitted when a real-estate transaction record is opened.",
)

# ---------------------------------------------------------------------------
# CRM / lead domain  (publisher: apps.crm — future)
# ---------------------------------------------------------------------------

registry.register(
    name="lead.created",
    version=1,
    required_payload_keys={"lead_id", "source", "assigned_agent_id"},
    description=(
        "Emitted when a new lead is created. "
        "assigned_agent_id may be empty string if unassigned."
    ),
)

# ---------------------------------------------------------------------------
# reservation domain  (publisher: apps.inventory.reservations)
# ---------------------------------------------------------------------------

registry.register(
    name="reservation.created",
    version=1,
    required_payload_keys={"reservation_id", "property_id", "agent_id"},
    description=(
        "Legacy CRM/property reservation stub. Prefer "
        "inventory.reservation.created for office inventory."
    ),
)

registry.register(
    name="inventory.reservation.created",
    version=1,
    required_payload_keys={
        "reservation_public_id",
        "item_public_id",
        "status",
        "quantity",
        "starts_at",
        "ends_at",
        "owner_id",
    },
    description="Emitted after an inventory reservation is committed.",
)

registry.register(
    name="inventory.reservation.cancelled",
    version=1,
    required_payload_keys={"reservation_public_id", "reason"},
    description="Emitted after an inventory reservation is cancelled.",
)

registry.register(
    name="inventory.reservation.approved",
    version=1,
    required_payload_keys={
        "reservation_public_id",
        "action",
        "from_status",
        "to_status",
    },
    description="Emitted after a requested reservation is approved.",
)

registry.register(
    name="inventory.reservation.denied",
    version=1,
    required_payload_keys={"reservation_public_id", "reason"},
    description="Emitted after a requested reservation is denied.",
)

registry.register(
    name="inventory.reservation.ready",
    version=1,
    required_payload_keys={"reservation_public_id"},
    description="Emitted when office marks a reservation ready for pickup.",
)

registry.register(
    name="inventory.reservation.checked_out",
    version=1,
    required_payload_keys={"reservation_public_id"},
    description="Emitted when office checks out a reservation.",
)

registry.register(
    name="inventory.reservation.returned",
    version=1,
    required_payload_keys={"reservation_public_id"},
    description="Emitted when office accepts a return.",
)

registry.register(
    name="inventory.reservation.completed",
    version=1,
    required_payload_keys={"reservation_public_id"},
    description="Emitted when office completes a returned reservation.",
)

registry.register(
    name="inventory.reservation.overdue",
    version=1,
    required_payload_keys={"reservation_public_id"},
    description="Emitted when a checked-out reservation passes its return deadline.",
)

registry.register(
    name="inventory.reservation.lost",
    version=1,
    required_payload_keys={"reservation_public_id", "reason"},
    description="Emitted when office marks a reservation lost.",
)

registry.register(
    name="inventory.reservation.damaged",
    version=1,
    required_payload_keys={"reservation_public_id", "reason"},
    description="Emitted when office marks a reservation damaged.",
)

registry.register(
    name="inventory.reservation.return_due_soon",
    version=1,
    required_payload_keys={
        "reservation_public_id",
        "office_id",
        "owner_id",
        "lead_day",
        "return_day",
        "policy_version",
        "occurred_at",
    },
    description=(
        "Emitted on an approved lead time before the inclusive return date while "
        "a reservation remains checked out. Beat tasks re-check status before "
        "publishing."
    ),
)

registry.register(
    name="inventory.reservation.return_overdue",
    version=1,
    required_payload_keys={
        "reservation_public_id",
        "office_id",
        "owner_id",
        "overdue_day",
        "return_day",
        "policy_version",
        "occurred_at",
    },
    description=(
        "Emitted on an approved cadence while a checked-out reservation remains "
        "overdue. Beat tasks re-check status before publishing."
    ),
)

registry.register(
    name="inventory.reservation.return_overdue_staff",
    version=1,
    required_payload_keys={
        "reservation_public_id",
        "office_id",
        "owner_id",
        "overdue_day",
        "return_day",
        "policy_version",
        "occurred_at",
        "staff_ids",
    },
    description=(
        "Escalates an overdue return to authorized office staff on an approved "
        "cadence. Beat tasks re-check status and recipient scope before publishing."
    ),
)

registry.register(
    name="inventory.reservation.lost_damaged_escalation",
    version=1,
    required_payload_keys={
        "reservation_public_id",
        "office_id",
        "owner_id",
        "escalation_day",
        "status",
        "policy_version",
        "occurred_at",
        "staff_ids",
    },
    description=(
        "Escalates lost or damaged reservations to office staff on an approved "
        "cadence. Beat tasks re-check status before publishing."
    ),
)

# ---------------------------------------------------------------------------
# announcement domain  (publisher: apps.announcements)
# ---------------------------------------------------------------------------

registry.register(
    name="announcement.published",
    version=1,
    required_payload_keys={
        "announcement_id",
        "category_code",
        "priority_code",
        "owner_office_id",
        "scope_level",
        "audience",
        "notify",
        "notification_priority",
    },
    description=(
        "Emitted when an announcement moves to published. Carries the stable "
        "taxonomy codes and the notification behaviour already resolved by "
        "apps.announcements.policy, so a consumer never re-derives policy "
        "from the row. audience is the resolved selector list — the rule, not "
        "a materialized recipient list; consumers re-evaluate it with "
        "apps.announcements.audience.recipients_for. category_code is null "
        "only on legacy rows that predate the published-requires-taxonomy "
        "constraint. visible_from is when the window opens — equal to the "
        "publication stamp for an immediate publish."
    ),
)

registry.register(
    name="announcement.scheduled",
    version=1,
    required_payload_keys={
        "announcement_id",
        "category_code",
        "priority_code",
        "owner_office_id",
        "scope_level",
        "audience",
        "notify",
        "notification_priority",
    },
    description=(
        "Emitted instead of announcement.published when the row is published "
        "with a publish_at still in the future. Same payload contract, so a "
        "consumer can handle both with one schema; visible_from is when the "
        "announcement actually becomes readable. Nothing should notify "
        "recipients on this event — the announcement is not open to them yet."
    ),
)

registry.register(
    name="announcement.unpublished",
    version=1,
    required_payload_keys={"announcement_id", "owner_office_id", "status"},
    description=(
        "An announcement was pulled back to draft by an authorized publisher. "
        "Consumers holding derived state should treat it as no longer "
        "readable from this moment."
    ),
)

registry.register(
    name="announcement.archived",
    version=1,
    required_payload_keys={"announcement_id", "owner_office_id", "status"},
    description=(
        "An announcement left the feed for good. The row, its media, and its "
        "history are retained; only visibility ends."
    ),
)

registry.register(
    name="announcement.restored",
    version=1,
    required_payload_keys={"announcement_id", "owner_office_id", "status"},
    description=(
        "An archived announcement was returned to draft. It is not readable "
        "again until it is deliberately republished."
    ),
)

# ---------------------------------------------------------------------------
# training domain  (publisher: apps.training.administration)
# ---------------------------------------------------------------------------

registry.register(
    name="training.published",
    version=1,
    required_payload_keys={
        "content_id",
        "owner_office_id",
        "scope_level",
        "status",
        "version_number",
        "version_family",
        "occurred_at",
    },
    description=(
        "Emitted when training content becomes published. Consumers holding "
        "derived library state should re-evaluate visibility from this moment."
    ),
)

registry.register(
    name="training.scheduled",
    version=1,
    required_payload_keys={
        "content_id",
        "owner_office_id",
        "scope_level",
        "status",
        "version_number",
        "version_family",
        "occurred_at",
    },
    description=(
        "Emitted instead of training.published when the row is published with "
        "a future publish_at. Nothing should notify recipients yet."
    ),
)

registry.register(
    name="training.unpublished",
    version=1,
    required_payload_keys={
        "content_id",
        "owner_office_id",
        "scope_level",
        "status",
        "version_number",
        "version_family",
        "occurred_at",
    },
    description=(
        "Training was pulled back to draft. Consumers should treat it as no "
        "longer readable from this moment."
    ),
)

registry.register(
    name="training.archived",
    version=1,
    required_payload_keys={
        "content_id",
        "owner_office_id",
        "scope_level",
        "status",
        "version_number",
        "version_family",
        "occurred_at",
    },
    description=(
        "Training left the library. The row, media, and progress history are "
        "retained; only visibility ends. Also emitted when a newer version "
        "supersedes a previously live sibling."
    ),
)

registry.register(
    name="training.restored",
    version=1,
    required_payload_keys={
        "content_id",
        "owner_office_id",
        "scope_level",
        "status",
        "version_number",
        "version_family",
        "occurred_at",
    },
    description=(
        "Archived training was returned to draft. It is not readable again "
        "until deliberately republished."
    ),
)

# ---------------------------------------------------------------------------
# inventory domain  (publisher: apps.inventory.services)
# ---------------------------------------------------------------------------

registry.register(
    name="inventory.item.created",
    version=1,
    required_payload_keys={"target_type", "target_id"},
    description="A new inventory item was created in scope.",
)

registry.register(
    name="inventory.item.updated",
    version=1,
    required_payload_keys={"target_type", "target_id"},
    description="An inventory item's catalog fields changed.",
)

registry.register(
    name="inventory.item.state_changed",
    version=1,
    required_payload_keys={"target_type", "target_id"},
    description="An inventory item's availability state changed.",
)

registry.register(
    name="inventory.item.retired",
    version=1,
    required_payload_keys={"target_type", "target_id"},
    description=(
        "An inventory item was retired. History is preserved and new "
        "reservations are blocked."
    ),
)

registry.register(
    name="inventory.item.transferred",
    version=1,
    required_payload_keys={"target_type", "target_id"},
    description=(
        "An inventory item moved between offices. Reservation history keyed "
        "by the item's public id is preserved."
    ),
)

# ---------------------------------------------------------------------------
# office-space domain  (publisher: apps.reservations.services)
# ---------------------------------------------------------------------------

registry.register(
    name="reservations.space.created",
    version=1,
    required_payload_keys={"target_type", "target_id"},
    description="A reservable office space was created within scoped ownership.",
)

registry.register(
    name="reservations.space.retired",
    version=1,
    required_payload_keys={"target_type", "target_id"},
    description=(
        "A space was retired without deleting its identity, schedules, or history."
    ),
)

registry.register(
    name="reservations.space.transferred",
    version=1,
    required_payload_keys={"target_type", "target_id"},
    description=(
        "A space moved offices through the explicit history-preserving operation."
    ),
)

registry.register(
    name="reservations.space.availability_blocked",
    version=1,
    required_payload_keys={"target_type", "target_id"},
    description="A holiday, maintenance, closure, or administrative hold was added.",
)

registry.register(
    name="reservations.booking.created",
    version=1,
    required_payload_keys={"target_type", "target_id"},
    description="A room reservation was created after authoritative validation.",
)

registry.register(
    name="reservations.booking.cancelled",
    version=1,
    required_payload_keys={"target_type", "target_id"},
    description="A room reservation was cancelled and its capacity released.",
)

registry.register(
    name="reservations.booking.rescheduled",
    version=1,
    required_payload_keys={"target_type", "target_id"},
    description="A room reservation moved atomically to a newly validated interval.",
)

registry.register(
    name="reservations.booking.approved",
    version=1,
    required_payload_keys={"target_type", "target_id"},
    description="A pending room reservation was approved within office scope.",
)

registry.register(
    name="reservations.booking.denied",
    version=1,
    required_payload_keys={"target_type", "target_id"},
    description="A pending room reservation was denied and its capacity released.",
)
