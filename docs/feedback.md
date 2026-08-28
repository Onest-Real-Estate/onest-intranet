# Feedback and support

Self-service intake for bug reports, ideas, content corrections, access issues,
and general help, plus the triage queue behind it. Lives in `apps/feedback`.

## Permissions

| Codename | What it opens |
| --- | --- |
| *(none)* | **Submitting.** Every authenticated person may report a problem with the tool they are told to use |
| `web.view_feedback` | Read feedback in scope. Does **not** open the inbox — that needs triage |
| `web.triage_feedback` | Read other people's tickets, move the lifecycle, set priority, convert to a task |
| `web.assign_feedback` | Set or clear the assignee |
| `web.note_feedback` | Write staff-only notes |

Submission is deliberately ungated. Putting a grant in front of the support
form means the people most likely to hit a permission bug are the ones who
cannot report it.

## Diagnostics — what is captured, and what is scrubbed

`apps/feedback/diagnostics.py` is the security core. Three rules, in order:

1. **Minimise.** The client may send exactly five browser facts — `viewport`,
   `locale`, `timezone`, `platform`, `browser` — and each must match a declared
   shape. There is no passthrough dictionary, so a future frontend cannot widen
   the capture by adding a key.
2. **Redact.** The page URL is the one field that routinely carries secrets:
   reset tokens, invite codes, signed links, SSO state. Query parameters are
   dropped unless they are on a short allowlist; an allowlisted key still loses
   a *value* that looks like a credential (JWT, long opaque string, `sk_`/`ghp_`
   prefixes) and is stored as `[redacted]` so a triager can see a parameter
   existed without learning it. **The fragment never survives.**
3. **Disclose.** `disclosure_lines()` generates the form's promise from the same
   constants that do the capturing, so the two cannot drift apart.

Same-origin is enforced **server-side**. A URL on another host is refused, not
stored — a ticket claiming to come from a page we do not serve is either a bug
or somebody shaping the record.

## Submission

- **Idempotent** on a client-supplied `submission_key` (unique column). A
  double-clicked button, a retried request, and a replayed POST all return the
  first ticket. The check runs **before** the rate limiter, so a retrying
  browser cannot lock somebody out of the form. A genuine race is absorbed by
  the unique constraint: the loser reads the winner's row.
- **Rate limited** to 8 submissions per 15 minutes, keyed by user rather than
  IP, cache-backed so a restart forgives. The error names the wait and offers
  the alternative — an error the reader cannot act on just becomes a support
  ticket about the support form.
- **Office is snapshotted** at submission. The submitter may move office later,
  and re-reading it live would silently move old tickets between queues.
- **Urgency seeds priority.** The submitter says how urgent it is *for them*; a
  triager sets queue priority separately. Both are kept — conflating them
  teaches people to always pick the top option.

### Screenshots

One image, in `private_storage`, with **no public URL and no signed link**.
Validation reuses `apps.announcements.media.inspect_upload`: extension check,
type sniffed from the leading bytes, and the decompression-bomb ceiling applied
before any decode, so a `.png` whose bytes are a script never reaches storage.

A screenshot of a broken page routinely contains another person's record, so
the file is streamed by a view that re-authorizes against the parent ticket on
every request rather than handing out anything durable.

## Scope

`FeedbackTicket.objects.for_reader(user, access=…, can_triage=…)` is the only
place visibility is decided, and it runs before counting or serialization.

Two audiences share it:

- a **submitter** sees their own tickets and nothing else, whatever office they
  are in — "who else complained" is not a question the reporter gets to ask;
- **support staff** see tickets in their office/region reach, or company-wide.

`can_triage` is passed in rather than derived, so a caller cannot forget that
reading somebody else's ticket is a *granted* capability. Office reach alone
opens nothing. Assignment is a personal grant: being handed a ticket lets you
read it even outside your reach.

## Lifecycle

```
New ──► Triaged ──► In progress ──► Resolved ──► Closed
 │         │             │  ▲
 └─────────┴──► Needs info ─┘          (Resolved / Closed ──► reopen)
```

Shorter than the operational-task lifecycle on purpose: a support ticket is a
conversation with somebody who is waiting, and finer states would be internal
process leaking into a queue the submitter can also see.

- **Needs info requires a question.** A request for information with nothing in
  it is a ticket that stalls. The text is stored as a **visible** note — it is
  for the submitter. Staff reasoning goes through `add_note(internal=True)`.
- **Concurrency:** `expected_status` under a row lock raises `ConcurrentUpdate`
  rather than overwriting a decision the caller never saw. Repeating a
  transition is a no-op — no second audit event, no second notice.
- Every create, transition, assignment, and conversion writes an `AuditEvent`
  **after commit**. `AUDIT_FIELDS` excludes the summary and description: an
  audit row states what changed, and copying the body would make a second,
  differently-scoped copy of protected content.

## Internal notes

`internal=True` is an authorization boundary, not a display hint.
`services.visible_notes` excludes them **in the queryset**, before a payload
builder can see one. A submitter may reply on their own ticket with no grant;
writing in the staff channel needs `note_feedback`.

Notification titles are generated from the event, never from a note body, so a
staff-only note cannot escape through an email subject line.

## Conversion to an operational task

`services.convert_to_task` raises the work the ticket is asking for, through
`apps.operational_tasks`. Three properties:

- **Idempotent twice over.** It returns early when the ticket already carries a
  task id, and the task module's `create_task` is keyed on `source_reference`,
  so a race still lands on one row.
- **No file crosses.** The screenshot stays under this module's policy; a task
  reader is not automatically entitled to it. The link is the reference, which
  each side re-authorizes independently.
- **The task module's own grant still applies.** Holding feedback triage does
  not by itself let somebody create tasks.

The link is stored as the task's public id rather than a foreign key, so the
two modules stay independently deployable and neither blocks the other's
migrations.

## Surface

| Route | Page | Who |
| --- | --- | --- |
| `/support/feedback` | The form | Anybody signed in |
| `/support/feedback/mine` | Their own reports | Anybody signed in |
| `/support/feedback/<id>` | One ticket | Submitter or a triager in scope |
| `/support/feedback/<id>/screenshot/<id>` | The image, streamed | Re-authorized per request |
| `/operations/feedback` | The triage inbox | `web.triage_feedback` |
| `/operations/feedback/<id>/{transition,assign,priority,convert}` | Triage writes | `web.triage_feedback` |

**Where staff find it.** *Feedback*, under **Governance & support** in the
administration rail. Held by system admins, principal brokers, broker admins,
and IT support. A manager holding only `view_feedback` does **not** reach it —
the inbox lists other people's reports, which is what `triage_feedback` grants.

The assignee picker is scoped **before** serialization like every other list,
so it never becomes a company-wide staff directory for somebody whose reach is
one branch. Candidates are people who actually hold the triage permission,
asked of the permission rather than of a role name.

**Where people find it.** Two entry points, both always present:

- a pinned **Get help** row at the foot of the sidebar, above the account card
  — help is the one destination whose value is being findable the moment
  something goes wrong, and burying it in the scrolling list means the reader
  who needs it most scrolls past everything that just failed them;
- the **?** control in the top bar, which opens a menu offering *Get help* and
  *My reports*. When `HUB_HELP_URL` is configured, the external help centre is
  added *beside* those rather than instead — "how does this work" and "this is
  broken" are different questions. That control used to be inert whenever no
  external URL was set, which is the state every deployment starts in.

Both triggers append `?from=<current path>`. `document.referrer` is empty for
an Inertia visit — which is every visit here — so capturing the page at the
click is the only thing that actually works. The value is scrubbed and
same-origin checked when the form renders *and* again on submit; a hostile one
is dropped rather than refused, because this is the page somebody reaches when
something is already broken.

**Contacts.** Below the form, the office's real IT support, admin, and branch
manager assignments — the same records Office Info reads. An office with none
shows no section at all: a fabricated contact is worse than none.

The form posts as a **native form**, not through the Inertia router: a
screenshot is multipart, and nothing the reader typed sits in client state a
failed save could lose. The submission key is minted once per mount, so a
double-clicked button lands on one ticket.

The detail page serves both audiences from one component. The difference is
entirely in the props — internal notes are filtered server-side, diagnostics
are omitted for a reader who cannot triage, and `transitions` arrives narrowed.
Nothing on the page decides any of it.
