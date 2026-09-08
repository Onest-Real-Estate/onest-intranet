import { Head, Link, useForm, usePage } from "@inertiajs/react";
import {
  ArrowLeft,
  CheckCircle2,
  Download,
  Lock,
  MessageSquare,
  Paperclip,
} from "lucide-react";

import {
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
import type {
  ITSupportTicketPageProps,
  SupportAttachment,
  SupportReply,
} from "@/types";

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

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function ReplyRow({ reply }: { reply: SupportReply }) {
  return (
    <li
      className={cn(
        "grid gap-1.5 rounded-lg border p-3",
        reply.internal
          ? "border-chip-warning-edge bg-chip-warning"
          : reply.isResolution
            ? "border-chip-success-edge bg-chip-success"
            : "border-border/70 bg-card",
      )}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
        <span className="font-medium">{reply.author?.name ?? "Removed user"}</span>
        <span className="text-muted-foreground">{formatMoment(reply.createdAt)}</span>
        {reply.internal ? (
          // Said in words, not only by the tint: an IT-only note that reads as
          // ordinary because somebody cannot see the colour is the failure this
          // whole channel exists to avoid.
          <span className="text-warning-ink inline-flex items-center gap-1 font-medium">
            <Lock className="size-3" aria-hidden />
            Internal — not shown to the requester
          </span>
        ) : null}
        {reply.isResolution ? (
          <span className="text-success inline-flex items-center gap-1 font-medium">
            <CheckCircle2 className="size-3" aria-hidden />
            Resolution
          </span>
        ) : null}
      </div>
      <p className="text-sm leading-6 whitespace-pre-line">{reply.body}</p>
    </li>
  );
}

/** One file, reached only through the authorized download route. */
function AttachmentRow({
  ticketId,
  file,
}: {
  ticketId: string;
  file: SupportAttachment;
}) {
  return (
    <li className="border-border/70 bg-card flex items-center gap-3 rounded-lg border p-3">
      <Paperclip className="text-muted-foreground size-4 shrink-0" aria-hidden />
      <div className="grid min-w-0 flex-1 gap-0.5">
        <span className="truncate text-sm font-medium">{file.displayName}</span>
        <span className="text-muted-foreground flex flex-wrap items-center gap-x-2 text-xs">
          <span>{formatBytes(file.byteSize)}</span>
          <span aria-hidden>·</span>
          <span>{file.uploadedBy?.name ?? "Removed user"}</span>
          {file.internal ? (
            <span className="text-warning-ink inline-flex items-center gap-1 font-medium">
              <Lock className="size-3" aria-hidden />
              Internal — IT only
            </span>
          ) : null}
        </span>
      </div>
      <Button asChild variant="outline" size="sm">
        {/* A plain anchor: a download, not an in-app visit. The server
            re-authorizes the reader against the parent ticket every time. */}
        <a
          href={routes.it_support_attachment(ticketId, file.id)}
          download={file.displayName}
        >
          <Download aria-hidden />
          Download
        </a>
      </Button>
    </li>
  );
}

/**
 * One ticket, read by two audiences from one page.
 *
 * A requester and a triager see the same component; what differs is what the
 * server put in the payload and what `can` permits. There is deliberately no
 * second detail page, because a second page is a second place to get the
 * internal-note rule wrong.
 */
export default function ITSupportTicket() {
  const { ticket, can, assignees, options, errors, user, csrfToken } =
    usePage<ITSupportTicketPageProps>().props;

  const moveForm = useForm({
    status: "",
    expectedStatus: ticket.status.code,
    note: "",
  });
  const replyForm = useForm({ body: "", internal: false });
  const assignForm = useForm({
    assignee: ticket.assignee ? String(ticket.assignee.id) : "",
    expectedAssignee: ticket.assignee ? String(ticket.assignee.id) : "",
  });
  const priorityForm = useForm({ priority: ticket.priority.code });

  function move(target: string, requiresNote: boolean) {
    if (requiresNote && !moveForm.data.note.trim()) {
      moveForm.setError("note", "Explain the change so the requester knows why.");
      return;
    }
    moveForm.transform((data) => ({
      ...data,
      status: target,
      expectedStatus: ticket.status.code,
    }));
    moveForm.post(routes.it_support_transition(ticket.id), {
      preserveScroll: true,
      onSuccess: () => moveForm.reset("note"),
    });
  }

  function reassign(next: string) {
    assignForm.setData("assignee", next);
    assignForm.transform((data) => ({ ...data, assignee: next }));
    assignForm.post(routes.it_support_assign(ticket.id), { preserveScroll: true });
  }

  const needsNote = ticket.transitions.some((option) => option.requiresNote);

  return (
    <div className="grid gap-8">
      <Head title={`${ticket.reference} · ${ticket.subject}`} />
      <PageHeader
        title={ticket.subject}
        meta={
          <>
            <span className="font-medium tabular-nums">{ticket.reference}</span>
            <span aria-hidden>·</span>
            <span>{ticket.category.label}</span>
          </>
        }
        actions={
          <Button asChild variant="outline">
            <Link href={can.triage ? routes.admin_it_support() : routes.it_support()}>
              <ArrowLeft aria-hidden />
              {can.triage ? "All tickets" : "My requests"}
            </Link>
          </Button>
        }
      />

      <div className="grid items-start gap-6 @4xl:grid-cols-[minmax(0,1fr)_21rem]">
        <div className="grid content-start gap-6">
          <SurfaceCard>
            <PanelHeader
              divided
              title="Request"
              meta={
                <span className="flex items-center gap-2">
                  <StatusBadge status={ticket.status} />
                  <StatusBadge status={ticket.priority} />
                </span>
              }
            />
            <SurfaceCardContent className="grid gap-4">
              <p className="max-w-measure text-sm leading-6 whitespace-pre-line">
                {ticket.description}
              </p>
              {ticket.deviceInfo || ticket.pageUrl ? (
                // Staff-only, and the server already withheld it from anybody
                // else — this is the render of a field a requester never receives.
                <dl className="border-border/70 text-muted-foreground grid gap-1 border-t pt-3 text-xs">
                  {ticket.deviceInfo ? (
                    <div className="flex gap-2">
                      <dt className="font-medium">Device</dt>
                      <dd className="min-w-0 break-words">{ticket.deviceInfo}</dd>
                    </div>
                  ) : null}
                  {ticket.pageUrl ? (
                    <div className="flex gap-2">
                      <dt className="font-medium">Page</dt>
                      <dd className="min-w-0 break-all">{ticket.pageUrl}</dd>
                    </div>
                  ) : null}
                </dl>
              ) : null}
            </SurfaceCardContent>
          </SurfaceCard>

          <SurfaceCard>
            <PanelHeader
              divided
              title="Conversation"
              description="Oldest first. IT-only notes are marked."
            />
            <SurfaceCardContent className="grid gap-4">
              {ticket.replies.length > 0 ? (
                <ul className="grid gap-2">
                  {ticket.replies.map((reply) => (
                    <ReplyRow key={reply.id} reply={reply} />
                  ))}
                </ul>
              ) : (
                <EmptyState
                  compact
                  tone="muted"
                  icon={MessageSquare}
                  title="Nothing said yet"
                  description="Replies between you and IT appear here."
                />
              )}

              {can.reply ? (
                <form
                  className="grid gap-3"
                  onSubmit={(event) => {
                    event.preventDefault();
                    replyForm.post(routes.it_support_reply(ticket.id), {
                      preserveScroll: true,
                      onSuccess: () => replyForm.reset(),
                    });
                  }}
                >
                  <FormField>
                    <FormLabel htmlFor="reply-body">Add a reply</FormLabel>
                    <Textarea
                      id="reply-body"
                      rows={3}
                      value={replyForm.data.body}
                      onChange={(event) =>
                        replyForm.setData("body", event.target.value)
                      }
                      aria-invalid={Boolean(errors.fields.body) || undefined}
                    />
                    <FormFieldError
                      id="reply-body-error"
                      message={errors.fields.body?.[0]}
                    />
                  </FormField>
                  {can.note ? (
                    <label
                      htmlFor="reply-internal"
                      className="flex items-center gap-2 text-sm"
                    >
                      <Checkbox
                        id="reply-internal"
                        checked={replyForm.data.internal}
                        onCheckedChange={(next) =>
                          replyForm.setData("internal", next === true)
                        }
                      />
                      Internal note — IT only
                    </label>
                  ) : null}
                  <div>
                    <Button
                      type="submit"
                      size="sm"
                      disabled={replyForm.processing || !replyForm.data.body.trim()}
                    >
                      {replyForm.processing ? "Sending…" : "Send reply"}
                    </Button>
                  </div>
                </form>
              ) : null}
            </SurfaceCardContent>
          </SurfaceCard>

          <SurfaceCard>
            <PanelHeader
              divided
              title="Attachments"
              description="Files live in protected storage and are re-authorized on every download."
            />
            <SurfaceCardContent className="grid gap-4">
              {ticket.attachments.length > 0 ? (
                <ul className="grid gap-2">
                  {ticket.attachments.map((file) => (
                    <AttachmentRow key={file.id} ticketId={ticket.id} file={file} />
                  ))}
                </ul>
              ) : (
                <EmptyState
                  compact
                  tone="muted"
                  icon={Paperclip}
                  title="No files attached"
                  description="Screenshots, logs, and documents appear here."
                />
              )}

              {can.reply ? (
                // Native multipart POST: one code path for uploads, and a
                // refusal comes back as an ordinary 422 re-render of this page.
                <form
                  method="post"
                  action={routes.it_support_attach(ticket.id)}
                  encType="multipart/form-data"
                  className="grid gap-3"
                >
                  <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
                  <FormField>
                    <FormLabel htmlFor="attachment-file">Attach a file</FormLabel>
                    <input
                      id="attachment-file"
                      name="file"
                      type="file"
                      required
                      className="border-input file:text-foreground focus-visible:border-ring focus-visible:ring-ring/50 flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-xs file:mr-3 file:border-0 file:bg-transparent file:text-sm file:font-medium focus-visible:ring-[3px] focus-visible:outline-none"
                      aria-describedby="attachment-help"
                    />
                    <FormDescription id="attachment-help">
                      Up to 10 MB, five files per ticket.
                    </FormDescription>
                    <FormFieldError
                      id="attachment-error"
                      message={errors.fields.file?.[0]}
                    />
                  </FormField>
                  {can.note ? (
                    <label
                      htmlFor="attachment-internal"
                      className="flex items-center gap-2 text-sm"
                    >
                      <input
                        id="attachment-internal"
                        name="internal"
                        type="checkbox"
                        value="1"
                        className="accent-primary size-4"
                      />
                      Internal file — IT only
                    </label>
                  ) : null}
                  <div>
                    <Button type="submit" size="sm" variant="outline">
                      <Paperclip aria-hidden />
                      Attach
                    </Button>
                  </div>
                </form>
              ) : null}
            </SurfaceCardContent>
          </SurfaceCard>
        </div>

        <aside className="grid content-start gap-6">
          <SurfaceCard>
            <PanelHeader divided title="Details" />
            <SurfaceCardContent className="grid gap-4">
              {can.assign ? (
                <FormField>
                  <FormLabel htmlFor="ticket-assignee">Assigned to</FormLabel>
                  <div className="flex flex-wrap items-center gap-2">
                    <NativeSelect
                      id="ticket-assignee"
                      className="flex-1"
                      value={assignForm.data.assignee}
                      disabled={assignForm.processing}
                      onChange={(event) => reassign(event.target.value)}
                      aria-invalid={Boolean(errors.fields.assignee) || undefined}
                    >
                      <option value="">Unassigned</option>
                      {assignees.map((person) => (
                        <option key={person.id} value={String(person.id)}>
                          {person.name}
                        </option>
                      ))}
                    </NativeSelect>
                    {user && ticket.assignee?.id !== user.id ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={assignForm.processing}
                        onClick={() => reassign(String(user.id))}
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

              {can.triage ? (
                <FormField>
                  <FormLabel htmlFor="ticket-priority">Priority</FormLabel>
                  <NativeSelect
                    id="ticket-priority"
                    value={priorityForm.data.priority}
                    disabled={priorityForm.processing}
                    onChange={(event) => {
                      const next = event.target.value;
                      priorityForm.setData("priority", next);
                      priorityForm.transform((data) => ({ ...data, priority: next }));
                      priorityForm.post(routes.it_support_priority(ticket.id), {
                        preserveScroll: true,
                      });
                    }}
                  >
                    {options.priorities.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </NativeSelect>
                </FormField>
              ) : null}

              <dl className="grid gap-4">
                {can.assign ? null : (
                  <ReadOnlyValue label="Assigned to">
                    {ticket.assignee?.name ?? "Not yet assigned"}
                  </ReadOnlyValue>
                )}
                <ReadOnlyValue label="Raised by">
                  {ticket.submitter?.name ?? "—"}
                </ReadOnlyValue>
                {ticket.aboutUser ? (
                  <ReadOnlyValue label="About">{ticket.aboutUser.name}</ReadOnlyValue>
                ) : null}
                {ticket.office ? (
                  <ReadOnlyValue label="Office">{ticket.office.name}</ReadOnlyValue>
                ) : null}
                {ticket.location ? (
                  <ReadOnlyValue label="Location">{ticket.location}</ReadOnlyValue>
                ) : null}
                <ReadOnlyValue label="Preferred contact">
                  {ticket.preferredContact.label}
                </ReadOnlyValue>
                <ReadOnlyValue label="Opened">
                  {formatMoment(ticket.createdAt)}
                </ReadOnlyValue>
                {ticket.resolvedAt ? (
                  <ReadOnlyValue label="Resolved">
                    {formatMoment(ticket.resolvedAt)}
                  </ReadOnlyValue>
                ) : null}
              </dl>
            </SurfaceCardContent>
          </SurfaceCard>

          {ticket.transitions.length > 0 ? (
            <SurfaceCard>
              <PanelHeader
                divided
                title="Move this ticket"
                description="Only the moves you may make are shown."
              />
              <SurfaceCardContent className="grid gap-3">
                {needsNote ? (
                  <FormField>
                    <FormLabel htmlFor="move-note" optional>
                      Note
                    </FormLabel>
                    <Textarea
                      id="move-note"
                      rows={2}
                      value={moveForm.data.note}
                      onChange={(event) => moveForm.setData("note", event.target.value)}
                    />
                    <FormDescription id="move-note-help">
                      Asking the requester for more, and resolving, both need one. A
                      resolution note is shown to them.
                    </FormDescription>
                    <FormFieldError
                      id="move-note-error"
                      message={moveForm.errors.note ?? errors.fields.note?.[0]}
                    />
                  </FormField>
                ) : null}
                <FormFieldError
                  id="move-status-error"
                  message={errors.fields.status?.[0]}
                />
                <div className="flex flex-wrap gap-2">
                  {ticket.transitions.map((option) => (
                    <Button
                      key={option.target}
                      type="button"
                      size="sm"
                      variant={option.tone === "success" ? "default" : "outline"}
                      disabled={moveForm.processing}
                      onClick={() => move(option.target, option.requiresNote)}
                    >
                      {option.label}
                    </Button>
                  ))}
                </div>
              </SurfaceCardContent>
            </SurfaceCard>
          ) : null}
        </aside>
      </div>
    </div>
  );
}

ITSupportTicket.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Support ticket",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "IT support", href: routes.it_support() },
          { label: "Ticket" },
        ],
        back: { label: "Back to IT support", href: routes.it_support() },
      },
    },
  ] as const;
