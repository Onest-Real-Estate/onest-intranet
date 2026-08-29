import { Head, Link, useForm, usePage } from "@inertiajs/react";
import {
  ArrowLeft,
  Building2,
  CalendarClock,
  Download,
  Lock,
  MessageSquare,
  Paperclip,
  TriangleAlert,
  UserRound,
} from "lucide-react";
import { useRef } from "react";

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
import { IconWell } from "@/components/IconWell";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import type {
  OperationalTaskDetailPageProps,
  TaskAttachment,
  TaskComment,
} from "@/types";

const ACCESS = { all: ["web.view_operational_tasks"] };

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

function CommentRow({ comment }: { comment: TaskComment }) {
  return (
    <li
      className={cn(
        "grid gap-1.5 rounded-lg border p-3",
        comment.internal
          ? "border-chip-warning-edge bg-chip-warning"
          : "border-border/70 bg-card",
      )}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
        <span className="font-medium">{comment.author?.name ?? "Removed user"}</span>
        <span className="text-muted-foreground">{formatMoment(comment.createdAt)}</span>
        {comment.internal ? (
          // Said in words, not only by the tint: a staff-only note that reads
          // as ordinary because somebody cannot see the colour is the failure
          // mode this whole channel exists to avoid.
          <span className="text-warning-ink inline-flex items-center gap-1 font-medium">
            <Lock className="size-3" aria-hidden />
            Internal — not shown to the reporter
          </span>
        ) : null}
      </div>
      <p className="text-sm leading-6 whitespace-pre-line">{comment.body}</p>
    </li>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/**
 * One file, reached only through the authorized download route.
 *
 * A plain `<a>` rather than an Inertia `<Link>` on purpose: this is a file
 * download, not an in-app visit, and the server re-authorizes the reader
 * against the parent task on every request. There is no permanent URL to hold.
 */
function AttachmentRow({ taskId, file }: { taskId: string; file: TaskAttachment }) {
  return (
    <li className="border-border/70 bg-card flex items-center gap-3 rounded-lg border p-3">
      <IconWell
        icon={Paperclip}
        tone="muted"
        className="size-8 shrink-0"
        iconClassName="size-4"
      />
      <div className="grid min-w-0 flex-1 gap-0.5">
        <span className="truncate text-sm font-medium">{file.displayName}</span>
        <span className="text-muted-foreground flex flex-wrap items-center gap-x-2 text-xs">
          <span>{formatBytes(file.byteSize)}</span>
          <span aria-hidden>·</span>
          <span>{file.uploadedBy?.name ?? "Removed user"}</span>
          {file.internal ? (
            // Said in words, not only by the icon: a staff-only file that reads
            // as ordinary is the failure this channel exists to prevent.
            <span className="text-warning-ink inline-flex items-center gap-1 font-medium">
              <Lock className="size-3" aria-hidden />
              Internal — staff only
            </span>
          ) : null}
        </span>
      </div>
      <Button asChild variant="outline" size="sm">
        <a
          href={routes.operational_task_attachment(taskId, file.id)}
          download={file.displayName}
        >
          <Download aria-hidden />
          <span className="sr-only">Download </span>
          Download
        </a>
      </Button>
    </li>
  );
}

/**
 * One task, and every move its reader is actually allowed to make.
 *
 * `task.transitions` arrives already filtered to this actor, and the service
 * re-checks each one on submit — the buttons are a convenience, never the
 * authorization. Each transition posts `expectedStatus`, so a stale tab cannot
 * move a task somebody else already moved: the server answers 409 and
 * re-renders from the stored row.
 */
export default function OperationalTaskDetail() {
  const { task, can, assignees, errors, user, csrfToken } =
    usePage<OperationalTaskDetailPageProps>().props;

  const transitionForm = useForm({ status: "", expectedStatus: task.status, note: "" });
  const commentForm = useForm({ body: "", internal: false });
  const assignForm = useForm({
    assignee: task.assignee ? String(task.assignee.id) : "",
    // The caller's view of the world, re-checked under a row lock: a stale tab
    // is told it lost the race rather than overwriting a decision it never saw.
    expectedAssignee: task.assignee ? String(task.assignee.id) : "",
  });
  const uploadInput = useRef<HTMLInputElement>(null);

  function reassign(next: string) {
    // Both, deliberately: `setData` moves the controlled `<select>` now so the
    // reader sees their own choice while the request is in flight, and
    // `transform` guarantees the posted value regardless of when that state
    // update lands.
    assignForm.setData("assignee", next);
    assignForm.transform((data) => ({ ...data, assignee: next }));
    assignForm.post(routes.operational_task_assign(task.id), {
      preserveScroll: true,
    });
  }

  function move(target: string, requiresNote: boolean) {
    transitionForm.transform((data) => ({
      ...data,
      status: target,
      expectedStatus: task.status,
    }));
    if (requiresNote && !transitionForm.data.note.trim()) {
      transitionForm.setError(
        "note",
        "Explain the change so the next reader knows what happened.",
      );
      return;
    }
    transitionForm.post(routes.operational_task_transition(task.id), {
      preserveScroll: true,
      onSuccess: () => transitionForm.reset("note"),
    });
  }

  const needsNote = task.transitions.some((option) => option.requiresNote);

  return (
    <PermissionRequired permission={ACCESS}>
      <div className="grid gap-8">
        <Head title={`${task.reference} · ${task.title}`} />

        <PageHeader
          title={task.title}
          meta={
            <>
              <span className="font-medium tabular-nums">{task.reference}</span>
              <span aria-hidden>·</span>
              <span>{task.category.label}</span>
            </>
          }
          actions={
            <Button asChild variant="outline">
              <Link href={routes.operational_tasks()}>
                <ArrowLeft aria-hidden />
                All tasks
              </Link>
            </Button>
          }
        />

        {task.isOverdue ? (
          <Callout icon={TriangleAlert} tone="warning">
            This task is past its due date of {formatMoment(task.dueAt)}.
          </Callout>
        ) : null}

        <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="grid content-start gap-6">
            <SurfaceCard>
              <PanelHeader
                divided
                title="Detail"
                meta={
                  <span className="flex items-center gap-2">
                    <StatusBadge status={task.status} />
                    <StatusBadge status={task.priority} />
                  </span>
                }
              />
              <SurfaceCardContent className="grid gap-4">
                {task.description ? (
                  <p className="text-sm leading-6 whitespace-pre-line">
                    {task.description}
                  </p>
                ) : (
                  <p className="text-muted-foreground text-sm">
                    No description was written.
                  </p>
                )}
                {task.sourceReference ? (
                  <p className="text-muted-foreground text-xs">
                    Converted from {task.source} reference {task.sourceReference}.
                  </p>
                ) : null}
              </SurfaceCardContent>
            </SurfaceCard>

            <SurfaceCard>
              <PanelHeader
                divided
                title="Activity"
                description="Comments on this task, oldest first."
              />
              <SurfaceCardContent className="grid gap-4">
                {task.comments.length > 0 ? (
                  <ul className="grid gap-2">
                    {task.comments.map((comment) => (
                      <CommentRow key={comment.id} comment={comment} />
                    ))}
                  </ul>
                ) : (
                  <EmptyState
                    compact
                    tone="muted"
                    icon={MessageSquare}
                    title="No comments yet"
                    description="Notes and updates on this task appear here."
                  />
                )}

                {can.comment ? (
                  <form
                    className="grid gap-3"
                    onSubmit={(event) => {
                      event.preventDefault();
                      commentForm.post(routes.operational_task_comment(task.id), {
                        preserveScroll: true,
                        onSuccess: () => commentForm.reset(),
                      });
                    }}
                  >
                    <FormField>
                      <FormLabel htmlFor="comment-body">Add a comment</FormLabel>
                      <Textarea
                        id="comment-body"
                        rows={3}
                        value={commentForm.data.body}
                        onChange={(event) =>
                          commentForm.setData("body", event.target.value)
                        }
                        aria-invalid={Boolean(errors.fields.body) || undefined}
                      />
                      <FormFieldError
                        id="comment-body-error"
                        message={errors.fields.body?.[0]}
                      />
                    </FormField>
                    {can.manage ? (
                      <label
                        htmlFor="comment-internal"
                        className="flex items-center gap-2 text-sm"
                      >
                        <Checkbox
                          id="comment-internal"
                          checked={commentForm.data.internal}
                          onCheckedChange={(next) =>
                            commentForm.setData("internal", next === true)
                          }
                        />
                        Internal note — staff only
                      </label>
                    ) : null}
                    <div>
                      <Button
                        type="submit"
                        size="sm"
                        disabled={
                          commentForm.processing || !commentForm.data.body.trim()
                        }
                      >
                        {commentForm.processing ? "Posting…" : "Post comment"}
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
                {task.attachments.length > 0 ? (
                  <ul className="grid gap-2">
                    {task.attachments.map((file) => (
                      <AttachmentRow key={file.id} taskId={task.id} file={file} />
                    ))}
                  </ul>
                ) : (
                  <EmptyState
                    compact
                    tone="muted"
                    icon={Paperclip}
                    title="No files attached"
                    description="Logs, screenshots, and documents for this task appear here."
                  />
                )}

                {can.comment ? (
                  // A native multipart POST rather than an Inertia visit: a file
                  // upload has no second code path this way, and a refusal comes
                  // back as an ordinary 422 re-render of this page.
                  <form
                    method="post"
                    action={routes.operational_task_attach(task.id)}
                    encType="multipart/form-data"
                    className="grid gap-3"
                  >
                    <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
                    <FormField>
                      <FormLabel htmlFor="attachment-file">Attach a file</FormLabel>
                      <input
                        ref={uploadInput}
                        id="attachment-file"
                        name="file"
                        type="file"
                        required
                        className="border-input file:text-foreground flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-xs file:mr-3 file:border-0 file:bg-transparent file:text-sm file:font-medium focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] focus-visible:outline-none"
                        aria-invalid={Boolean(errors.fields.file) || undefined}
                        aria-describedby="attachment-file-help"
                      />
                      <FormDescription id="attachment-file-help">
                        Up to 10 MB. PDF, Office documents, images, logs, CSV, and plain
                        text.
                      </FormDescription>
                      <FormFieldError
                        id="attachment-file-error"
                        message={errors.fields.file?.[0]}
                      />
                    </FormField>
                    {can.manage ? (
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
                        Internal file — staff only
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
              <PanelHeader divided title="Assignment" />
              <SurfaceCardContent className="grid gap-4">
                {can.assign ? (
                  <FormField>
                    <FormLabel htmlFor="task-assignee">Assignee</FormLabel>
                    <div className="flex flex-wrap items-center gap-2">
                      <NativeSelect
                        id="task-assignee"
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
                      {user && task.assignee?.id !== user.id ? (
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
                      id="task-assignee-error"
                      message={errors.fields.assignee?.[0]}
                    />
                  </FormField>
                ) : null}
                <dl className="grid gap-4">
                  {can.assign ? null : (
                    <ReadOnlyValue label="Assignee">
                      <span className="flex items-center gap-2">
                        <IconWell
                          icon={UserRound}
                          tone="muted"
                          className="size-7"
                          iconClassName="size-3.5"
                        />
                        {task.assignee?.name ?? "Unassigned"}
                      </span>
                    </ReadOnlyValue>
                  )}
                  <ReadOnlyValue label="Reported by">
                    {task.reporter?.name ?? "—"}
                  </ReadOnlyValue>
                  <ReadOnlyValue label="Office">
                    <span className="flex items-center gap-2">
                      <Building2 className="size-4 shrink-0" aria-hidden />
                      {task.office.name}
                    </span>
                  </ReadOnlyValue>
                  <ReadOnlyValue label="Due">
                    <span className="flex items-center gap-2">
                      <CalendarClock className="size-4 shrink-0" aria-hidden />
                      {formatMoment(task.dueAt)}
                    </span>
                  </ReadOnlyValue>
                  <ReadOnlyValue label="Created">
                    {formatMoment(task.createdAt)}
                  </ReadOnlyValue>
                </dl>
              </SurfaceCardContent>
            </SurfaceCard>

            {task.transitions.length > 0 ? (
              <SurfaceCard>
                <PanelHeader
                  divided
                  title="Move this task"
                  description="Only the moves you may make are shown."
                />
                <SurfaceCardContent className="grid gap-3">
                  {needsNote ? (
                    <FormField>
                      <FormLabel htmlFor="transition-note" optional>
                        Note
                      </FormLabel>
                      <Textarea
                        id="transition-note"
                        rows={2}
                        value={transitionForm.data.note}
                        onChange={(event) =>
                          transitionForm.setData("note", event.target.value)
                        }
                      />
                      <FormDescription id="transition-note-help">
                        Blocking, waiting, and cancelling each need one. It is stored as
                        an internal note.
                      </FormDescription>
                      <FormFieldError
                        id="transition-note-error"
                        message={transitionForm.errors.note ?? errors.fields.note?.[0]}
                      />
                    </FormField>
                  ) : null}
                  <FormFieldError
                    id="transition-status-error"
                    message={errors.fields.status?.[0]}
                  />
                  <div className="flex flex-wrap gap-2">
                    {task.transitions.map((option) => (
                      <Button
                        key={option.target}
                        type="button"
                        size="sm"
                        variant={option.tone === "success" ? "default" : "outline"}
                        disabled={transitionForm.processing}
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
    </PermissionRequired>
  );
}

OperationalTaskDetail.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Task",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Tasks", href: routes.operational_tasks() },
          { label: "Task" },
        ],
        back: { label: "Back to tasks", href: routes.operational_tasks() },
      },
    },
  ] as const;
