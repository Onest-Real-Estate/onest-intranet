# IT Support

Internal help desk for equipment, accounts, and access. Users raise a request at
`/support/it`; the IT team works the queue at `/operations/it-support`. Lives in
`apps/it_support`.

> **Not the same thing as Feedback.** `apps/feedback` is about the *product* — a
> bug, an idea, something out of date. IT Support is about the *equipment and
> accounts somebody needs to work today*: a printer, a Wi-Fi drop, a locked
> account. They have different categories and, importantly, **different
> readers**: `view_it_support` is held by IT staff, and folding these tickets
> into the feedback inbox would hand every feedback triager a view of them. The
> operations registry reserved this module its own destination, permission, and
> scope rule before it was built.

## Permissions

| Codename | What it opens |
| --- | --- |
| *(none)* | **Raising** a ticket and reading your own |
| `web.view_it_support` | The IT queue |
| `web.triage_it_support` | Move tickets through the lifecycle, set priority |
| `web.assign_it_support` | Set or clear the owner |
| `web.note_it_support` | Write IT-only notes and attach IT-only files |

Submitting needs **no grant** on purpose: gating it means the people most likely
to hit an account or access bug are the ones who cannot report it.

## Scope

`SupportTicket.objects.for_reader(user, access=…, can_triage=…)` is the **only**
place ticket visibility is decided, and it runs before counting, serialization,
or search.

Two audiences, deliberately different:

- **Everybody** sees tickets they raised *and* tickets raised **about** them, so
  a new agent can watch their own account setup without holding an IT grant.
- **A triager** additionally sees every ticket inside their office reach.

Without the grant, office reach buys nothing: being a branch manager is not a
reason to read a colleague's password problem. `can_triage` is also the
*caller's intent* — the requester-facing pages pass `False`, so an IT staffer
reading `/support/it` sees their own tickets, not the whole queue.

## Lifecycle

```
New ──► Open ──► In progress ──► Resolved ──► Closed
          │         │  ▲                ▲
          └─────────┴──┴─► Waiting for your reply
                       (Resolved / Closed ──► reopen)
```

Declared once in `taxonomy.TRANSITIONS`. `services.transition` is the only
writer of `status`.

- **Notes are required** on "Ask the requester" and "Resolve". A resolution note
  is recorded as `is_resolution` and shown to the requester — it is what they
  are actually told, so it is not buried as one more line in the thread.
- **The requester may Resume and Reopen.** Answering a question IT asked is the
  one move the person waiting can make, and "it is still broken" is the whole
  point of telling somebody it was fixed. They may **not** close or prioritise:
  a requester who can mark their own ticket urgent makes the field meaningless
  within a week.
- A database constraint keeps `closed_at` and a terminal status in step, and
  another forbids a reply that is both internal and a resolution.

### Concurrency

`transition(..., expected_status=…)` and `assign(..., expected_assignee_id=…)`
take the caller's view of the world. Under a row lock a mismatch raises
`ConcurrentUpdate` rather than overwriting a decision the caller never saw.
Repeating a move that already happened is a **no-op** — no second write, no
second audit event, no second notice.

## Internal notes and diagnostics

`internal=True` is an authorization boundary, not a display hint.
`services.visible_replies` / `visible_attachments` exclude internal rows **in
the queryset**, so no serializer change can turn an IT note into a response
field.

`deviceInfo` and `pageUrl` are withheld from a requester in `payloads`. They are
of no use to them and describe their own machine, which is not something to echo
back onto a page they may screen-share.

## Attachments

Up to **5 files, 10 MB each**, from a closed extension allowlist. Stored in
`private_storage` with **no URL in the payload**; the only read path is
`GET /support/it/<id>/attachments/<id>`, which re-authorizes on that request. An
IT-only file is a **404, not a 403**, for a requester — a 403 would confirm it
exists.

The media type comes from `services.ATTACHMENT_MEDIA_TYPES`, which the allowlist
is derived from. It is **not** read from `mimetypes`: that consults the host's
own MIME database, and a type that depends on which machine accepted the upload
is a header this hub would later serve back.

## Idempotency

`submission_key` is generated once per form render. A double-clicked button, a
retried request, and a browser replaying the POST all return the first ticket;
`created` tells the caller whether to re-run side effects. A cache-backed rate
limit allows 10 submissions per person per 15 minutes — enough that a bad
morning is not rationed, few enough to stop a script.

## Notifications

Delivered through `apps/notifications` using the **`administrative`** type. The
requester hears about receipt, assignment, IT replies, waiting-on-you, resolved,
and closed. The desk hears about new tickets, escalations, and requester
replies — but **only the assignee**: fanning "new ticket" out to every
grant-holder makes the inbox the thing people mute first, and the queue is where
unassigned work is found.

Nobody is notified about their own action. `resolve_ticket_notifications`
re-runs the module's scope filter every time an inbox is opened, so losing a
grant retires every notice it covered without rewriting delivered rows.

## Onboarding

`SupportCategory.ONBOARDING` ("New agent setup") is how somebody asks IT to
provision a new agent's accounts and apps, and `about_user` records who the
request is for when that is not the submitter.

The **checklist itself is not here.** Per-agent, per-tool provisioning state
lives on `user.OnboardingToolSetup` and is worked from the New Agent List; this
category is the request that asks for the work, not a second copy of the
progress. Keeping one source of truth is the whole point — two would disagree
within a week.

## Surface

| Route | Who | What |
| --- | --- | --- |
| `/support/it` | Everyone | Raise a request; your own tickets |
| `/support/it/<id>` | Requester **or** triager | One ticket |
| `/operations/it-support` | `view_it_support` | The queue, filters, metrics |

The detail page is **shared**. A requester and a triager render the same
component; what differs is what the server put in the payload and what `can`
permits. A second detail page would be a second place to get the internal-note
rule wrong.

Queue metrics (open, urgent, unassigned, waiting, resolved this week) are counted
on the **scoped** queryset, so a triager whose reach is one branch sees that
branch's figures rather than the brokerage's.
