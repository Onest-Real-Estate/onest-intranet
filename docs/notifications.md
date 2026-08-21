# Notifications

The shared in-app notification domain: one record per recipient, a header
badge, and a full notification centre at `/notifications`. Contracts,
transactions, announcements, training, inventory, rooms, leads, and
administrative workflows all deliver through the same producer service — they
do not write notification rows themselves.

Code: `apps/notifications/`. Frontend: `frontend/pages/Notifications.tsx`,
`frontend/components/notifications/`.

## The two rules everything else follows from

**1. The row is a pointer, not a copy.** A notification stores a fixed title
that names nobody ("An onboarding case was assigned to you") and provenance
for the record it concerns. It never stores the client, property, document, or
person. The detail a reader sees is resolved from the source record *on every
read*, so a revoked permission, an office transfer, or a deleted record
removes the detail from notifications delivered months earlier — with nothing
going back to rewrite old rows.

**2. The destination is a typed action, not a URL.** Producers name an action
from the allowlist in `apps/notifications/actions.py`; the path is reversed at
render time and the destination enforces its own policy on arrival. A stale
notification cannot widen access, and a producer cannot put an off-site link
in somebody's inbox.

## Data model

`Notification` (`apps/notifications/models.py`) — one row per recipient.

| Field | Role |
| --- | --- |
| `public_id` | Opaque UUID used in every URL; the integer key is never exposed |
| `recipient` | The only identity input; every query starts here |
| `notification_type` | Producing domain — the reader's filter, not an authorization input |
| `event_key` | Producing domain event, for observability |
| `title` | Fixed producer copy. Non-sensitive by contract |
| `priority` | 1 critical → 4 low, matching the action-item contract |
| `is_mandatory` | Must be acknowledged individually (see below) |
| `source_module` / `source_record_type` / `source_record_id` | Provenance for the resolver |
| `action_key` / `action_args` | Allowlisted destination, reversed at render time |
| `dedupe_key` | Idempotency key, unique per recipient |
| `created_at` / `available_at` / `expires_at` / `read_at` / `archived_at` | Lifecycle |

Indexes cover `(recipient, read_at, archived_at, available_at)` for the badge
and `(recipient, archived_at | type | priority, available_at)` for the centre,
so every listed query is bounded and indexed.

**Lifecycle states.** A row is *scheduled* until `available_at` (invisible),
then *live*. Past `expires_at` it is *expired*: excluded from the badge —
counting something the reader cannot clear is a badge that never goes away —
and shown in the "All" view with no detail and no destination. *Archived* rows
leave the inbox for the archive filter. Nothing is ever deleted on a reader's
behalf; `purge_expired_notifications` is the only removal, and only for rows
whose expiry has passed.

## Producing

Domain modules publish the domain event they were already publishing. The
consumer in `apps/notifications/consumers.py` turns registered events into
deliveries, which means the side effect is after-commit, retried, and
idempotent for free (see `apps/audit/tasks.dispatch_event`).

```python
# apps/notifications/producers.py
EVENT_PRODUCERS = {
    "user.onboarding.owner_assigned": onboarding_owner_assigned,
    "user.account.state_changed": account_reactivated,
}
```

To add a producer:

1. Register the event in `apps/audit/catalog.py` if it is new.
2. Add a builder returning `list[NotificationRequest]` and register it in
   `EVENT_PRODUCERS`.
3. Ship a source resolver for its module (below). Without one the notification
   is refused at delivery — that is the intended fail-closed behaviour, not a
   bug to work around.

**Idempotency.** `dedupe_key` is unique per recipient. Default to the event id
(`f"{envelope.name}:{envelope.id}"`): a replay is a no-op while a genuine
second occurrence is a new notification. Key on record identity instead when
repeated signals about one record should collapse into a single row. Never key
on a timestamp.

**What the producer service validates** (`apps/notifications/service.py`):

- the recipient exists and is active;
- the source domain vouches for that recipient's access *now*;
- the delivery is not already expired;
- a mandatory notification carries an action and no expiry;
- the idempotency key is present and stable.

Anything that fails is dropped with a log line, not raised at the workflow
that triggered it.

## Bulk audiences

`deliver_to_audience(template, recipient_ids)` queues `fan_out_notifications`
on commit and returns. No HTTP request ever writes an audience: an announcement
to a thousand agents is a thousand rows, chunked `FAN_OUT_CHUNK_SIZE` at a
time, each chunk handing its tail to a fresh task. Re-running a chunk after a
worker crash adds nobody twice.

## Source resolvers

`apps/notifications/sources.py` holds the registry; `resolvers.py` holds the
shipped ones. A resolver answers, for a batch of notifications and one reader:
is this still visible to them, what should it say, and may the action be
offered?

```python
def resolve(user, notifications) -> dict[UUID, SourceResolution]: ...


register_resolver("contract", resolve)
```

Resolvers are **batched** — one call per source module per page, never one per
row — so a page costs a bounded number of queries. Unknown modules fail
closed: their notifications list with a title, a reason, and nothing else.

Shipped resolvers:

| Module | Checks | Result |
| --- | --- | --- |
| `onboarding` | `web.view_new_agents` and the agent is still in the reader's administrative scope | "Onboarding for <name>" and the case destination |
| *(none)* | Self-contained notification about the reader themselves | Title only; action still re-authorizes at the destination |

The unavailable copy is deliberately identical for a lost grant, an
out-of-scope record, and a deleted one. Distinguishing them would answer a
question about a record the reader is no longer allowed to ask about.

## Reading and mutating

Every endpoint is self-scoped; none accepts a recipient identifier.

| Route | Method | What |
| --- | --- | --- |
| `notifications` | GET | The centre: filtered, paginated (20/page) |
| `notification_state` | POST | Mark one read / unread / archived |
| `notification_read_all` | POST | Sweep unread, except mandatory |
| `notification_summary` | GET | JSON badge counts for the caller |

Mutations are **idempotent**: repeating an applied action succeeds. Read state
changes with a filtered `UPDATE`, never a read-modify-write, so two tabs
cannot double-count. Counts always come from the database.

An id belonging to somebody else redirects exactly like an id that does not
exist — confirming that a notification exists is itself a disclosure.

**Mandatory policy.** A mandatory notification is excluded from mark-all-read
and cannot be archived while unread. A sweep that can clear a compliance
acknowledgement is not an acknowledgement.

## Frontend

`notifications` is a shared Inertia prop on every page: `unreadCount`,
`mandatoryCount`, `href`. `NotificationBell` renders it in the header, exposes
the count as text in the control's label (never colour alone), mirrors changes
into a polite live region, and re-polls `notification_summary` every 60s while
the tab is visible. A failed poll keeps the last known figure and marks it
stale rather than blanking the badge. Replacing the poll with a socket means
replacing the `poll()` body — the announcement behaviour is already in place.

The centre's list prop is `notificationList`, **not** `notifications`: a page
prop of that name would shadow the shared badge on this page alone.

States the page covers: unread/read (marker *and* the word), required, stale
action with its reason, expired, archived, empty (three different reasons),
refused mutation (422 with the message), and in-flight rows (`aria-busy`,
disabled controls).

## Testing

`apps/notifications/tests/` covers idempotency, self-only access, concurrent
read state, pagination and counts, source revocation, safe actions, fan-out
chunking and replay, and the page's query budget.
`frontend/pages/Notifications.test.tsx` and
`frontend/components/notifications/NotificationBell.test.tsx` cover the reader
states, the mutation payloads, polling, and accessibility.
