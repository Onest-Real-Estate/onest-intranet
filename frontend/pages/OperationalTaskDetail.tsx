import { Head, Link, useForm, usePage } from "@inertiajs/react";
import {
  ArrowLeft,
  Building2,
  CalendarClock,
  Lock,
  MessageSquare,
  TriangleAlert,
  UserRound,
} from "lucide-react";

import {
  Callout,
  EmptyState,
  FormDescription,
  FormField,
  FormFieldError,
  FormLabel,
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
import type { OperationalTaskDetailPageProps, TaskComment } from "@/types";

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
  const { task, can, errors } = usePage<OperationalTaskDetailPageProps>().props;

  const transitionForm = useForm({ status: "", expectedStatus: task.status, note: "" });
  const commentForm = useForm({ body: "", internal: false });

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
          </div>

          <aside className="grid content-start gap-6">
            <SurfaceCard>
              <PanelHeader divided title="Assignment" />
              <SurfaceCardContent className="grid gap-4">
                <dl className="grid gap-4">
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
