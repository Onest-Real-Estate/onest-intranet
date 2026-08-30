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
    "contract.pdf_ready": contract_pdf_ready,
    "contract.issued": contract_issued,
    "contract.viewed": contract_viewed,
    "contract.signed": contract_signed,
    "contract.activated": contract_activated,
    "contract.superseded": contract_superseded,
    "contract.terminated": contract_terminated,
    "contract.expired": contract_expired,
    "contract.generation_error": contract_generation_error,
    "contract.signature_reminder": contract_signature_reminder,
    "contract.expiration_warning": contract_expiration_warning,
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
| `contract` | Reader still reaches the contract via `accessible_contract_queryset`; signature reminders fail closed once the row is no longer signable | Status-derived detail and My Contract / workspace action |
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
| `notification_preferences` | GET | The reader's own channel settings |
| `notification_preferences_submit` | POST | Save them |

Mutations are **idempotent**: repeating an applied action succeeds. Read state
changes with a filtered `UPDATE`, never a read-modify-write, so two tabs
cannot double-count. Counts always come from the database.

An id belonging to somebody else redirects exactly like an id that does not
exist — confirming that a notification exists is itself a disclosure.

**Mandatory policy.** A mandatory notification is excluded from mark-all-read
and cannot be archived while unread. A sweep that can clear a compliance
acknowledgement is not an acknowledgement.

## Preferences

Code: `apps/notifications/categories.py` (the catalog),
`apps/notifications/preferences.py` (resolution and saving),
`frontend/pages/NotificationPreferences.tsx`.

**Categories are notification types.** One vocabulary, not two:
`categories.py` asserts at import that the category registry and
`NotificationType` are the same set, so a type with no reviewed category — or
a category governing nothing — fails at startup rather than at send time.

**Channels.** `in_app` is the record of what was delivered and is *not*
configurable; a reader who could switch it off would have compliance
acknowledgements land nowhere. `email` is the channel this feature exists to
let people turn down. The model is a `{channel: {category: bool}}` map, so
adding a channel is a registry entry rather than a migration.

**Three rules decide every send**, applied in this order:

1. A notification with `is_mandatory` sends, in every category, whatever the
   reader stored. Legal, compliance, and security acknowledgements are not
   preferences.
2. A category marked `mandatory` sends. `account` is one — security notices
   about somebody's own access.
3. Everything else follows the stored choice, and an absent entry follows the
   category's `default_email`.

**Only decisions are stored.** `NotificationPreference.channels` holds what the
reader explicitly chose and nothing else. A stored full matrix would freeze
today's catalog into every row: "never chose" would be indistinguishable from
"chose off", and changing a default would silently not apply to anybody.

**A new category therefore starts at its registry default for everyone** until
each reader decides otherwise. Nothing migrates, nothing is reinterpreted. Add
the type to `contract.py`, add a `NotificationCategory`, and bump
`PREFERENCE_POLICY_VERSION` — the settings page then tells readers whose saved
version is behind that the list is longer than it was, without resetting
anything. The house default for a new category is `default_email=True`; a
high-volume stream ships `False` so it is opt-in (`inventory`, `room`, `lead`).

**Mandatory cannot be turned off by any request.** `NotificationPreferencesForm`
builds its fields from the registry, so a locked cell has no field — a crafted
post naming one is not rejected, it simply changes nothing. `normalize_stored`
drops locked cells on read too, so a hand-edited or restored row cannot switch
off a legal notice either. Unknown channels and categories are dropped rather
than raising: a settings page that 500s on an old row is one nobody can use to
fix the row.

The page sends the whole matrix, locked cells included, each arriving on,
disabled, and carrying the sentence that says why. A switch that is simply
absent reads as a channel that does not exist.

## Email delivery

Code: `apps/notifications/delivery.py` (the pipeline),
`apps/notifications/providers/` (pluggable push backends),
`apps/notifications/emails.py` (rendering), `templates/notifications/email/`,
`apps/notifications/tasks.py` (the three tasks).

### Pluggable push providers

Outbound channels implement `DeliveryProvider` and register in
`apps.notifications.providers.registry`. The shared ledger
(`NotificationEmail`) and claim/retry/sweep mechanics are channel-agnostic —
adding Microsoft Graph or Slack means registering a provider, not rewriting
producers.

| Provider | Channel key | Enabled when |
| --- | --- | --- |
| `EmailDeliveryProvider` | `email` | Always |
| `MicrosoftDeliveryProvider` | `microsoft` | `NOTIFICATION_MICROSOFT_ENABLED` + client id |
| `SlackDeliveryProvider` | `slack` | `NOTIFICATION_SLACK_ENABLED` + bot token |

Microsoft and Slack ship as dormant stubs: preferences hide them until enabled,
and `send` raises until a real Graph/Slack sender is approved. Email remains
the production push path.

The in-app notification is the domain fact. `NotificationEmail` is a *ledger*
for pushing a copy of it out, deliberately separate so nothing about a
deferred, bounced, or abandoned email touches the notification. A dead delivery
leaves the reader's inbox exactly as it was.

| Status | Meaning |
| --- | --- |
| `pending` | Queued; `next_attempt_at` says when it is due |
| `sending` | Claimed by a worker |
| `sent` | Delivered to the SMTP relay; `to_email` records where |
| `suppressed` | Deliberately not sent; `suppression_reason` says why |
| `failed` | Transport error, backing off for another attempt |
| `dead` | Attempt budget exhausted; audited and alerted |

`sent`, `suppressed`, and `dead` are terminal. Suppression is terminal on
purpose: "you unsubscribed", "you already read it", "the source withdrew
access" do not become untrue in a way that should resurrect the message.

**At most one send per recipient per channel per key.**
`(recipient, channel, delivery_key)` is unique and `delivery_key` *is* the
notification's `dedupe_key`, so a replayed event, a re-run fan-out chunk, and a
duplicated task all converge on one row. The row is then claimed with a
compare-and-set `UPDATE … WHERE status IN (pending, failed)` before the SMTP
call, so two workers racing produce one send and one no-op — without holding a
row lock across a mail conversation.

**After commit.** Rows are written inside the producing transaction; the worker
is only told from `transaction.on_commit`. A rolled-back workflow mails nobody,
and a broker outage logs rather than failing the originating request.

**Revalidated immediately before send** (`delivery.send_reason`) — account
state, the address itself, the notification's lifecycle, the preference, and
the source domain's willingness to vouch for the reader are all re-read, never
trusted from queue time. A reminder about something already read, archived, or
expired in the hub is suppressed rather than sent: by the time a retry lands,
that is usually exactly what it is.

**Retries are bounded and on the row**, not in Celery: five attempts with
60s / 5m / 15m / 1h / 3h backoff, then `dead` with an error log and a
`notification.email.failed` audit event carrying counts and keys only.
`send_notification_email` deliberately does not use Celery retry — one retry
ledger is auditable, two that can disagree is not.

**Recovery does not depend on the broker.** `sweep_notification_emails`
(schedule with celery beat) returns rows stuck in `sending` past 15 minutes to
the queue, then re-queues everything due from the database. A lost task, a
dropped queue, or a restarted worker costs a delay rather than a message.
`NotificationEmail` is registered read-only in the Django admin: recovery is a
queue operation, not a hand edit.

### What the message may contain

The body is the **fixed producer title**, its category, and a link back into
the hub. It is not a copy of the notification:

* **No source detail.** What the notification is about is resolved for a
  signed-in reader whose access is checked at that moment. Mail leaves the
  perimeter and is readable by whoever holds the mailbox.
* **No file links.** Sensitive files live behind short-lived authorized access;
  a URL in an email outlives the authorization that produced it. Mail links
  only ever point at an in-app path, which re-authenticates on arrival.
* **No off-site destinations.** `emails.absolute_url` accepts only a
  single-slash-rooted path on this deployment — `//host/x` and absolute URLs
  are refused — and joins it to `SITE_BASE_URL`. An action that no longer
  reverses degrades to the notification centre.
* The subject is whitespace-collapsed, so producer copy cannot inject a header.

Optional messages carry a link to the settings page; required ones say plainly
that they cannot be turned off.

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
`test_notification_preferences.py` covers the default matrix, the mandatory
override from both the form and a hand-edited row, unknown categories, and a
category added after a reader last saved.
`test_notification_email_delivery.py` covers after-commit queueing, one row per
recipient/channel/key, the claim under a concurrent worker, every suppression
reason, an address changed between queue and send, backoff to `dead` with its
audit event, stalled-claim recovery, and what the rendered message is allowed
to contain.
`frontend/pages/Notifications.test.tsx`,
`frontend/pages/NotificationPreferences.test.tsx`, and
`frontend/components/notifications/NotificationBell.test.tsx` cover the reader
states, the mutation payloads, polling, locked controls, and accessibility.
