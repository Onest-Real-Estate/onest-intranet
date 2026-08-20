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
# contract domain  (publisher: apps.contract — future)
# ---------------------------------------------------------------------------

registry.register(
    name="contract.created",
    version=1,
    required_payload_keys={"contract_id", "office_id", "agent_id"},
    description="Emitted when an agent creates a new contract draft.",
)

registry.register(
    name="contract.signed",
    version=1,
    required_payload_keys={"contract_id", "signer_id", "signed_at"},
    description="Emitted when all required parties have signed a contract.",
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
# reservation domain  (publisher: apps.reservation — future)
# ---------------------------------------------------------------------------

registry.register(
    name="reservation.created",
    version=1,
    required_payload_keys={"reservation_id", "property_id", "agent_id"},
    description="Emitted when a property reservation is recorded.",
)
