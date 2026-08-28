# Operational tasks

Internal work tracking for onboarding issues, permission requests, tool setup,
content updates, office setup, integration incidents, bugs, and support
follow-up. Lives in `apps/operational_tasks`.

> **Not the same thing as “Platform Tasks”.** `web.view_platform_tasks` and the
> `/operations/platform-tasks` destination are a *sanitized Celery job status*
> viewer: unscoped, low risk, read-only. This module is scoped work with
> assignees, comments, attachments, and an enforced lifecycle. They share a word
> and nothing else, which is why this module has its own permission family
> rather than reusing that grant — doing so would have silently widened four
> existing role bundles.

## Permissions

| Codename | What it opens |
| --- | --- |
| `web.view_operational_tasks` | Read tasks in scope |
| `web.manage_operational_tasks` | Create, transition, write internal notes, reopen |
| `web.assign_operational_tasks` | Set or clear the assignee |
| `web.comment_operational_tasks` | Post a visible comment (not an internal note) |

`manage` implies `assign`. `assign` alone exists for a dispatcher who routes
work without otherwise managing the queue.

## Scope

`OperationalTask.objects.for_reader(user, access=…)` is the **only** place task
visibility is decided, and it runs before counting, serialization, or search. A
later Python-side check would hide rows and still leak how many exist through a
total.

A reader sees a task when any of these hold:

1. company reach, or superuser;
2. the task’s office is in their office reach;
3. the task’s office is in a region they reach;
4. they reported it, are assigned it, or are named in `visible_to`.

The last group is the narrow personal grant: it opens **that record only** and
widens organisational reach by nothing. An agent keeps reading a task they
reported after moving office; they gain nothing else.

## Lifecycle

```
Open ──► In progress ──► Resolved ──► Closed
 │           │  ▲  │
 │           │  │  ├──► Blocked ──┐
 │           │  │  └──► Waiting ──┤
 │           │  └────────────────-┘
 └───────────┴──► Cancelled            (Closed / Cancelled ──► reopen)
```

Declared once in `taxonomy.TRANSITIONS`, which owns the source, target, who may
make the move, whether it needs a note, and whether it closes or reopens.
`services.transition` is the only writer of `status`.

- **Notes are required** on Blocked, Waiting, and Cancel. Each changes what
  somebody else should expect, so none may be silent. The note is stored as an
  **internal** comment — the reason for a staff decision is staff-only; the
  outcome reaches the reporter as a notification.
- **The assignee may progress their own work** (Start, Resolve, Block, Wait)
  without the management grant, but may not Close or Reopen. Finishing work and
  signing it off are different decisions.
- **Terminal states are `Closed` and `Cancelled`.** A terminal task leaves the
  board, stops emitting action items, and stops counting as overdue however far
  past its due date it sits.

### Concurrency

`transition(..., expected_status=…)` and `assign(..., expected_assignee_id=…)`
take the caller’s view of the world. Under a row lock, a mismatch raises
`ConcurrentUpdate` rather than overwriting a decision the caller never saw — a
stale board cannot drag a task somebody else already resolved.

Repeating a transition that already happened is a **no-op**: no second write,
no second audit event, no second notification.

`expected_assignee_id` uses a sentinel for “no opinion”, because an explicit
`None` is a real claim (“I believe this is unassigned”) worth verifying.

## Audit

Every create, transition, and assignment writes an `AuditEvent` **after
commit** — an event describing a change that rolled back is worse than no event.
`AUDIT_FIELDS` deliberately excludes `description` and comment bodies: an audit
record states *what changed*, and copying free text into it would create a
second, unscoped copy of content the task’s own permissions were protecting.

## Internal notes and attachments

`internal=True` is an authorization boundary, not a display hint.
`services.visible_comments` / `visible_attachments` exclude internal rows **in
the queryset**, before a payload builder can see one, so no serializer change
can turn a staff note into a response field. Attachments use
`private_storage`; there is no public URL.

## Conversion from feedback

`services.convert_from_feedback(feedback_reference=…)` is the seam the feedback
module (P1-078) calls. Two properties matter:

- **Idempotent.** A second conversion of the same reference returns the existing
  task. A retried Celery task, a double-clicked button, and a replayed event all
  land on the same row.
- **It copies no file.** A feedback screenshot stays in the feedback module’s
  protected storage under the feedback module’s policy; a task reader is not
  automatically entitled to it. The link is the reference, and source identity
  (`source` + `source_reference`) is kept forever.

## Notifications

Assignment and the reporter-facing status changes deliver through
`apps/notifications` using the **`administrative`** type — the type enum is a
closed set shared with the preference screen, and widening it for one module
would be a schema and UI change this work does not need.

Nobody is notified about their own action. Moves between two working states are
deliberately silent: a notice per drag trains people to ignore the inbox.

`resolve_task_notifications` re-runs the module’s scope filter every time an
inbox is opened, so losing an office assignment retires every notice about tasks
in it without anything rewriting delivered rows.

## Dashboard action items

`action_items.collect_task_actions` emits only tasks **assigned to** the reader
and only in `Open` / `In progress`. A blocked or waiting task is not something
the assignee can move, so it stays off the queue until it comes back to them.
Completion is derived from the task; there is no dashboard-side dismissal.

## Surface

`/operations/tasks` is the queue, in two layouts behind one route:

- **List** — paginated, filterable, columns dropping by *container* width.
- **Board** — grouped **server-side** into the lifecycle's fixed columns, so
  the order, the counts, and the empty columns are the same fact the list is
  reading. A client-side `groupBy` would silently drop a status the server
  knows about. The board is bounded at 200 rather than paginated: a column that
  quietly stops at 25 looks like the work is done.

`/operations/tasks/<public_id>` is the detail. `transitions` arrives already
narrowed to the moves the reader may make, each posts `expectedStatus`, and the
service re-checks every one — the buttons are a convenience, never the gate.
