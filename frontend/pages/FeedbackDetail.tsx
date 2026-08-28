import { Head, Link, useForm, usePage } from "@inertiajs/react";
import {
  ArrowLeft,
  ArrowUpRight,
  ImageIcon,
  Lock,
  MessageSquare,
  MonitorSmartphone,
} from "lucide-react";

import {
  Callout,
  EmptyState,
  FormDescription,
  FormField,
  FormFieldError,
  FormLabel,
  NativeSelect,
  PageHeader,
  PanelHeader,
  ReadOnlyValue,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import type { FeedbackDetailPageProps, FeedbackNote } from "@/types";

function formatMoment(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? "—"
    : parsed.toLocaleString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      });
}

function NoteRow({ note }: { note: FeedbackNote }) {
  return (
    <li
      className={cn(
        "grid gap-1.5 rounded-lg border p-3",
        note.internal
          ? "border-chip-warning-edge bg-chip-warning"
          : "border-border/70 bg-card",
      )}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
        <span className="font-medium">{note.author?.name ?? "Removed user"}</span>
        <span className="text-muted-foreground">{formatMoment(note.createdAt)}</span>
        {note.internal ? (
          // Said in words, not only by the tint. A staff-only note that reads
          // as ordinary because somebody cannot see the colour is exactly the
          // failure this channel exists to prevent.
          <span className="text-warning-ink inline-flex items-center gap-1 font-medium">
            <Lock className="size-3" aria-hidden />
            Internal — not shown to the reporter
          </span>
        ) : null}
      </div>
      <p className="text-sm leading-6 whitespace-pre-line">{note.body}</p>
    </li>
  );
}

/**
 * One ticket, from either side.
 *
 * The same page serves the submitter and support staff, and the difference is
 * entirely in the props: internal notes are filtered out server-side before
 * they reach here, diagnostics are omitted for a reader who cannot triage, and
 * `transitions` arrives already narrowed to the moves this actor may make.
 * Nothing on this page decides any of that.
 */
export default function FeedbackDetail() {
  const { ticket, can, assignees, priorities, errors } =
    usePage<FeedbackDetailPageProps>().props;
  const currentUserId = usePage<FeedbackDetailPageProps>().props.user?.id ?? null;

  const noteForm = useForm({ body: "", internal: false });
  const assignForm = useForm({ assignee: "" });
  const priorityForm = useForm({ priority: "" });
  const moveForm = useForm({
    status: "",
    expectedStatus: ticket.status.code,
    reply: "",
  });

  function move(target: string, requiresReply: boolean) {
    if (requiresReply && !moveForm.data.reply.trim()) {
      moveForm.setError(
        "reply",
        "Say what you need from them — a request with no question stalls.",
      );
      return;
    }
    moveForm.transform((data) => ({
      ...data,
      status: target,
      expectedStatus: ticket.status.code,
    }));
    moveForm.post(routes.feedback_transition(ticket.id), {
      preserveScroll: true,
      onSuccess: () => moveForm.reset("reply"),
    });
  }

  const needsReply = ticket.transitions.some((option) => option.requiresReply);

  return (
    <>
      <Head title={`${ticket.reference} · ${ticket.summary}`} />
      <div className="grid gap-8">
        <PageHeader
          title={ticket.summary}
          meta={
            <>
              <span className="font-medium tabular-nums">{ticket.reference}</span>
              <span aria-hidden>·</span>
              <span>{ticket.category.label}</span>
              <span aria-hidden>·</span>
              <span>Sent {formatMoment(ticket.createdAt)}</span>
            </>
          }
          actions={
            <Button asChild variant="outline">
              <Link
                href={can.triage ? routes.admin_feedback() : routes.feedback_mine()}
              >
                <ArrowLeft aria-hidden />
                {can.triage ? "Support inbox" : "My reports"}
              </Link>
            </Button>
          }
        />

        {ticket.status.code === "needs_info" ? (
          <Callout icon={MessageSquare} tone="warning">
            Support has asked a question below. Reply and they will pick it back up.
          </Callout>
        ) : null}

        <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="grid content-start gap-6">
            <SurfaceCard>
              <PanelHeader
                divided
                title="What was reported"
                meta={<StatusBadge status={ticket.status} />}
              />
              <SurfaceCardContent className="grid gap-4">
                <p className="text-sm leading-6 whitespace-pre-line">
                  {ticket.description}
                </p>
                {ticket.screenshots.length > 0 ? (
                  <div className="grid gap-2">
                    <p className="text-muted-foreground text-xs font-semibold tracking-[0.06em] uppercase">
                      Screenshot
                    </p>
                    {ticket.screenshots.map((shot) => (
                      <a
                        key={shot.id}
                        href={shot.href}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="border-border/70 hover:border-border-strong text-primary inline-flex items-center gap-2 rounded-lg border p-3 text-sm transition-colors duration-(--motion-fast)"
                      >
                        <ImageIcon className="size-4 shrink-0" aria-hidden />
                        <span className="truncate underline">{shot.displayName}</span>
                        <ArrowUpRight className="size-3.5 shrink-0" aria-hidden />
                      </a>
                    ))}
                  </div>
                ) : null}
              </SurfaceCardContent>
            </SurfaceCard>

            <SurfaceCard>
              <PanelHeader divided title="Conversation" />
              <SurfaceCardContent className="grid gap-4">
                {ticket.notes.length > 0 ? (
                  <ul className="grid gap-2">
                    {ticket.notes.map((note) => (
                      <NoteRow key={note.id} note={note} />
                    ))}
                  </ul>
                ) : (
                  <EmptyState
                    compact
                    tone="muted"
                    icon={MessageSquare}
                    title="Nothing yet"
                    description="Replies from support will appear here."
                  />
                )}

                <form
                  className="grid gap-3"
                  onSubmit={(event) => {
                    event.preventDefault();
                    noteForm.post(routes.feedback_note(ticket.id), {
                      preserveScroll: true,
                      onSuccess: () => noteForm.reset(),
                    });
                  }}
                >
                  <FormField>
                    <FormLabel htmlFor="note-body">
                      {can.triage ? "Reply or add a note" : "Reply"}
                    </FormLabel>
                    <Textarea
                      id="note-body"
                      rows={3}
                      value={noteForm.data.body}
                      onChange={(event) => noteForm.setData("body", event.target.value)}
                    />
                    <FormFieldError
                      id="note-body-error"
                      message={errors.fields.body?.[0]}
                    />
                  </FormField>
                  {can.note ? (
                    <label
  htmlFor="note-internal"
  className="flex items-center gap-2 text-sm"
>
                      <Checkbox
                        id="note-internal"
checked={noteForm.data.internal}
                        onCheckedChange={(next) =>
                          noteForm.setData("internal", next === true)
                        }
                      />
                      Internal note — the reporter will not see this
                    </label>
                  ) : null}
                  <div>
                    <Button
                      type="submit"
                      size="sm"
                      disabled={noteForm.processing || !noteForm.data.body.trim()}
                    >
                      {noteForm.processing ? "Sending…" : "Send"}
                    </Button>
                  </div>
                </form>
              </SurfaceCardContent>
            </SurfaceCard>
          </div>

          <aside className="grid content-start gap-6">
            <SurfaceCard>
              <PanelHeader divided title="Status" />
              <SurfaceCardContent>
                <dl className="grid gap-4">
                  <ReadOnlyValue label="Status">
                    <StatusBadge status={ticket.status} />
                  </ReadOnlyValue>
                  <ReadOnlyValue label="You said">{ticket.urgency.label}</ReadOnlyValue>
                  {can.triage ? (
                    <ReadOnlyValue label="Priority">
                      <StatusBadge status={ticket.priority} />
                    </ReadOnlyValue>
                  ) : null}
                  <ReadOnlyValue label="Assigned to">
                    {ticket.assignee?.name ?? "Not yet assigned"}
                  </ReadOnlyValue>
                  {can.triage ? (
                    <ReadOnlyValue label="Reported by">
                      {ticket.submitter?.name ?? "—"}
                      {ticket.office ? ` · ${ticket.office.name}` : ""}
                    </ReadOnlyValue>
                  ) : null}
                </dl>
              </SurfaceCardContent>
            </SurfaceCard>

            {/* Diagnostics are a triage tool and reach only somebody who can
                act on them. They are scrubbed server-side either way. */}
            {can.triage && ticket.diagnostics ? (
              <SurfaceCard state="read-only">
                <PanelHeader
                  divided
                  title="Diagnostics"
                  description="Captured with the report, with secrets removed."
                  meta={
                    <MonitorSmartphone
                      className="text-muted-foreground size-4"
                      aria-hidden
                    />
                  }
                />
                <SurfaceCardContent>
                  <dl className="grid gap-3">
                    <ReadOnlyValue label="Page">
                      <span className="break-all">
                        {ticket.diagnostics.pageUrl || "Not recorded"}
                      </span>
                    </ReadOnlyValue>
                    {Object.entries(ticket.diagnostics.metadata).map(([key, value]) => (
                      <ReadOnlyValue key={key} label={key}>
                        {value}
                      </ReadOnlyValue>
                    ))}
                  </dl>
                </SurfaceCardContent>
              </SurfaceCard>
            ) : null}

            {can.triage ? (
              <SurfaceCard>
                <PanelHeader
                  divided
                  title="Triage"
                  description="Only the moves you may make are shown."
                />
                <SurfaceCardContent className="grid gap-4">
                  {can.assign ? (
                    <FormField>
                      <FormLabel htmlFor="assignee">Assignee</FormLabel>
                      <div className="flex flex-wrap items-center gap-2">
                        <NativeSelect
                          id="assignee"
                          className="min-w-0 flex-1"
                          value={
                            assignForm.data.assignee ||
                            (ticket.assignee ? String(ticket.assignee.id) : "")
                          }
                          onChange={(event) => {
                            assignForm.setData("assignee", event.target.value);
                            // Submit on change: an assignment is one decision,
                            // and a select plus a Save button is two.
                            const chosen = event.target.value;
                            assignForm.transform(() => ({ assignee: chosen }));
                            assignForm.post(routes.feedback_assign(ticket.id), {
                              preserveScroll: true,
                            });
                          }}
                        >
                          <option value="">Unassigned</option>
                          {assignees.map((person) => (
                            <option key={person.id} value={String(person.id)}>
                              {person.name}
                            </option>
                          ))}
                        </NativeSelect>
                        {currentUserId !== null &&
                        ticket.assignee?.id !== currentUserId ? (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            disabled={assignForm.processing}
                            onClick={() => {
                              assignForm.transform(() => ({
                                assignee: String(currentUserId),
                              }));
                              assignForm.post(routes.feedback_assign(ticket.id), {
                                preserveScroll: true,
                              });
                            }}
                          >
                            Take it
                          </Button>
                        ) : null}
                      </div>
                      <FormFieldError
                        id="assignee-error"
                        message={errors.fields.assignee?.[0]}
                      />
                    </FormField>
                  ) : null}

                  <FormField>
                    <FormLabel htmlFor="priority">Priority</FormLabel>
                    <NativeSelect
                      id="priority"
                      value={priorityForm.data.priority || ticket.priority.code}
                      onChange={(event) => {
                        priorityForm.setData("priority", event.target.value);
                        const chosen = event.target.value;
                        priorityForm.transform(() => ({ priority: chosen }));
                        priorityForm.post(routes.feedback_prioritise(ticket.id), {
                          preserveScroll: true,
                        });
                      }}
                      aria-describedby="priority-help"
                    >
                      {priorities.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </NativeSelect>
                    <FormDescription id="priority-help">
                      Queue order. Separate from the urgency the reporter chose, which
                      stays on the ticket as what they said.
                    </FormDescription>
                    <FormFieldError
                      id="priority-error"
                      message={errors.fields.priority?.[0]}
                    />
                  </FormField>

                  {needsReply ? (
                    <FormField>
                      <FormLabel htmlFor="move-reply" optional>
                        Message to the reporter
                      </FormLabel>
                      <Textarea
                        id="move-reply"
                        rows={2}
                        value={moveForm.data.reply}
                        onChange={(event) =>
                          moveForm.setData("reply", event.target.value)
                        }
                      />
                      <FormFieldError
                        id="move-reply-error"
                        message={moveForm.errors.reply ?? errors.fields.reply?.[0]}
                      />
                    </FormField>
                  ) : null}
                  <FormFieldError
                    id="move-status-error"
                    message={errors.fields.status?.[0]}
                  />
                  {ticket.transitions.length > 0 ? (
                    <div className="flex flex-wrap gap-2">
                      {ticket.transitions.map((option) => (
                        <Button
                          key={option.target}
                          type="button"
                          size="sm"
                          variant={option.tone === "success" ? "default" : "outline"}
                          disabled={moveForm.processing}
                          onClick={() => move(option.target, option.requiresReply)}
                        >
                          {option.label}
                        </Button>
                      ))}
                    </div>
                  ) : (
                    // A ticket with nowhere legal to go still needs its
                    // assignee and priority reachable — those are not moves.
                    <p className="text-muted-foreground text-xs">
                      This ticket has no further moves from “{ticket.status.label}”.
                    </p>
                  )}
                  {ticket.convertedTaskId ? (
                    <p className="text-muted-foreground text-xs">
                      Converted to an operational task.
                    </p>
                  ) : (
                    <form
                      onSubmit={(event) => {
                        event.preventDefault();
                        moveForm.post(routes.feedback_convert(ticket.id), {
                          preserveScroll: true,
                        });
                      }}
                    >
                      <Button type="submit" size="sm" variant="outline">
                        Convert to a task
                      </Button>
                    </form>
                  )}
                </SurfaceCardContent>
              </SurfaceCard>
            ) : null}
          </aside>
        </div>
      </div>
    </>
  );
}

FeedbackDetail.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Report",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "My reports", href: routes.feedback_mine() },
          { label: "Report" },
        ],
      },
      variant: "standard",
    },
  ] as const;
