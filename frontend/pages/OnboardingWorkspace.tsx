import { Head, Link, router, usePage } from "@inertiajs/react";
import {
  Check,
  CircleAlert,
  Clock3,
  ExternalLink,
  LockKeyhole,
  Plus,
  ShieldCheck,
  UserRoundCheck,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  DateField,
  FormDescription,
  FormErrorSummary,
  FormField,
  FormLabel,
  FormSheet,
  FormSheetBody,
  PageHeader,
  PanelHeader,
  ReadOnlyValue,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { SelectField, TextField } from "@/components/profile/profile-fields";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Progress } from "@/components/ui/progress";
import { hasPermission } from "@/lib/permissions";
import { routes } from "@/lib/routes";
import { hasValidationErrors } from "@/lib/validation";
import type {
  FilterOption,
  OnboardingTool,
  OnboardingWorkspacePageProps,
} from "@/types";

function formatMoment(value: string | null): string {
  if (!value) return "Never";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "Never" : parsed.toLocaleString();
}

function formatDate(value: string | null): string {
  if (!value) return "Not set";
  const parsed = new Date(`${value}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? "Not set" : parsed.toLocaleDateString();
}

function ToolSetupForm({
  tool,
  userId,
  version,
  csrfToken,
  options,
  validation,
  editable,
}: {
  tool: OnboardingTool;
  userId: number;
  version: string;
  csrfToken: string;
  options: FilterOption[];
  validation: OnboardingWorkspacePageProps["validation"];
  editable: boolean;
}) {
  const [state, setState] = useState(tool.state);
  return (
    <form
      method="post"
      action={routes.new_agent_onboarding_tools(userId)}
      className="border-border/60 grid gap-3 border-b py-4 last:border-0 sm:grid-cols-[minmax(0,1fr)_11rem_auto] sm:items-end"
    >
      <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
      <input type="hidden" name="expected_version" value={version} />
      <input type="hidden" name="tool" value={tool.key} />
      <div className="grid gap-1">
        <span className="font-semibold">{tool.label}</span>
        <span className="text-muted-foreground text-xs">
          {tool.updatedBy
            ? `Updated by ${tool.updatedBy} · ${formatMoment(tool.updatedAt)}`
            : "No operational update yet"}
        </span>
      </div>
      <SelectField
        name="state"
        controlId={`${tool.key}_state`}
        label={`${tool.label} state`}
        value={state}
        onChange={setState}
        placeholder="Choose a state"
        options={options}
        validation={validation}
        disabled={!editable}
      />
      <Button type="submit" variant="outline" size="sm" disabled={!editable}>
        Save
      </Button>
    </form>
  );
}

export default function OnboardingWorkspace() {
  const {
    csrfToken,
    requestId,
    user: currentUser,
    onboarding,
    ownerOptions,
    toolStateOptions,
    activity,
    validation,
    privacy,
  } = usePage<OnboardingWorkspacePageProps>().props;
  const [owner, setOwner] = useState(onboarding.owner?.id.toString() ?? "");
  const [taskOpen, setTaskOpen] = useState(false);
  const [taskSubmitting, setTaskSubmitting] = useState(false);
  const taskFormRef = useRef<HTMLFormElement>(null);
  const summaryRef = useRef<HTMLDivElement>(null);
  const hasErrors = hasValidationErrors(validation);
  const canManage =
    onboarding.editable &&
    hasPermission(currentUser, { all: ["web.manage_new_agent_onboarding"] });
  const percent = onboarding.progress.total
    ? Math.round((onboarding.progress.complete / onboarding.progress.total) * 100)
    : 0;

  useEffect(() => {
    // While the task sheet is open its own summary has focus; yanking the
    // page behind the overlay would be disorienting.
    if (hasErrors && !taskOpen) summaryRef.current?.focus();
  }, [hasErrors, taskOpen]);

  /**
   * The create-task form posts through Inertia so a failed submit keeps the
   * sheet open with everything typed: the 422 re-renders this same page and
   * only the `validation` prop changes. Success closes the sheet and clears
   * the draft for next time.
   */
  function onCreateTaskSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTaskSubmitting(true);
    router.post(
      routes.new_agent_onboarding_tasks(onboarding.user.id),
      new FormData(event.currentTarget),
      {
        onSuccess: () => {
          setTaskOpen(false);
          taskFormRef.current?.reset();
        },
        onFinish: () => setTaskSubmitting(false),
      },
    );
  }

  return (
    <PermissionRequired permission={{ all: ["web.view_new_agents"] }}>
      <div className="grid gap-8">
        <Head title={`Onboarding · ${onboarding.user.name}`} />
        <PageHeader
          title={onboarding.user.name}
          description={`${onboarding.user.email} · ${onboarding.user.office ?? "No office"} · Starts ${formatDate(onboarding.user.startDate)}`}
          meta={<StatusBadge status={onboarding.overall} />}
        />

        <div ref={summaryRef} tabIndex={-1} className="outline-none">
          <FormErrorSummary
            errors={validation}
            labels={{
              owner: "Onboarding owner",
              title: "Task",
              due_on: "Due date",
              tool: "Tool",
              state: "Setup state",
            }}
          />
        </div>

        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_21rem] xl:items-start xl:gap-8">
          <main className="grid gap-6">
            <SurfaceCard className="border-border/70 rounded-(--radius-card) shadow-card">
              <PanelHeader
                title="Activation path"
                description="Source-owned milestones update from their systems; there are no manual completion boxes here."
                className="border-border/60 border-b pb-5"
                meta={
                  <span className="text-muted-foreground text-xs font-medium tabular-nums">
                    {onboarding.progress.complete} of {onboarding.progress.total}
                  </span>
                }
              />
              <SurfaceCardContent className="grid gap-5">
                <div className="grid gap-2">
                  <div className="flex items-center justify-between gap-3 text-sm">
                    <span className="font-medium">Activation progress</span>
                    <span className="text-muted-foreground tabular-nums">
                      {percent}%
                    </span>
                  </div>
                  <Progress value={percent} aria-label={`${percent}% complete`} />
                </div>
                <ol className="grid gap-1">
                  {onboarding.milestones.map((milestone) => (
                    <li
                      key={milestone.key}
                      className="border-border/60 grid gap-3 border-b py-4 last:border-0 sm:grid-cols-[1fr_auto] sm:items-center"
                    >
                      <div className="flex min-w-0 gap-3">
                        <span className="bg-muted mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg">
                          {milestone.status === "complete" ? (
                            <Check className="text-success size-4" aria-hidden />
                          ) : milestone.status === "blocked" ? (
                            <CircleAlert
                              className="text-destructive size-4"
                              aria-hidden
                            />
                          ) : (
                            <Clock3
                              className="text-muted-foreground size-4"
                              aria-hidden
                            />
                          )}
                        </span>
                        <div className="min-w-0">
                          <p className="font-semibold">{milestone.label}</p>
                          <p className="text-muted-foreground mt-1 text-sm leading-5">
                            {milestone.detail}
                          </p>
                          <p className="text-muted-foreground mt-1 text-xs">
                            Source: {milestone.source}
                            {milestone.updatedAt
                              ? ` · ${formatMoment(milestone.updatedAt)}`
                              : ""}
                          </p>
                        </div>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                        <StatusBadge
                          status={{
                            label: milestone.statusLabel,
                            tone: milestone.tone,
                          }}
                        />
                        {milestone.correction ? (
                          <Button variant="ghost" size="sm" asChild>
                            <Link href={milestone.correction.href}>
                              {milestone.correction.label}
                              <ExternalLink className="size-3.5" aria-hidden />
                            </Link>
                          </Button>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ol>
              </SurfaceCardContent>
            </SurfaceCard>

            <SurfaceCard className="border-border/70 rounded-(--radius-card) shadow-card">
              <PanelHeader
                title="Tool setup"
                description="Only the approved operational states below are editable."
                className="border-border/60 border-b pb-5"
              />
              <SurfaceCardContent className="grid gap-1">
                {onboarding.tools.map((tool) => (
                  <ToolSetupForm
                    key={tool.key}
                    tool={tool}
                    userId={onboarding.user.id}
                    version={onboarding.version}
                    csrfToken={csrfToken}
                    options={toolStateOptions}
                    validation={validation}
                    editable={canManage}
                  />
                ))}
              </SurfaceCardContent>
            </SurfaceCard>

            <SurfaceCard className="border-border/70 rounded-(--radius-card) shadow-card">
              <PanelHeader
                title="Operational tasks"
                description="Tasks coordinate work; they never override a derived milestone."
                className="border-border/60 border-b pb-5"
                meta={
                  <span className="text-muted-foreground text-xs font-medium tabular-nums">
                    {onboarding.tasks.length} open
                  </span>
                }
              />
              <SurfaceCardContent className="grid gap-5">
                {onboarding.tasks.length ? (
                  <ul className="grid gap-2">
                    {onboarding.tasks.map((task) => (
                      <li
                        key={task.id}
                        className="border-border/60 bg-muted/25 flex flex-col gap-3 rounded-lg border p-4 sm:flex-row sm:items-center sm:justify-between"
                      >
                        <div className="min-w-0">
                          <p className="flex items-center gap-2 font-semibold">
                            {task.isBlocking ? (
                              <CircleAlert
                                className="text-destructive size-4 shrink-0"
                                aria-label="Blocks activation"
                              />
                            ) : null}
                            {task.title}
                          </p>
                          <p className="text-muted-foreground mt-1 text-xs">
                            {task.dueOn ? `Due ${formatDate(task.dueOn)} · ` : ""}
                            Added by {task.createdBy}
                          </p>
                        </div>
                        <form
                          method="post"
                          action={routes.new_agent_onboarding_tasks(onboarding.user.id)}
                        >
                          <input
                            type="hidden"
                            name="csrfmiddlewaretoken"
                            value={csrfToken}
                          />
                          <input type="hidden" name="action" value="resolve" />
                          <input type="hidden" name="task" value={task.id} />
                          <input
                            type="hidden"
                            name="expected_version"
                            value={onboarding.version}
                          />
                          <Button
                            type="submit"
                            variant="outline"
                            size="sm"
                            disabled={!canManage}
                          >
                            <Check className="size-3.5" aria-hidden />
                            Resolve
                          </Button>
                        </form>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="bg-muted/30 rounded-lg px-4 py-5 text-sm">
                    <p className="font-semibold">No operational tasks are open.</p>
                    <p className="text-muted-foreground mt-1">
                      Source milestones may still need attention; use their correction
                      workflows above.
                    </p>
                  </div>
                )}

                {canManage ? (
                  <div className="border-border/60 flex justify-end border-t pt-5">
                    <Button type="button" onClick={() => setTaskOpen(true)}>
                      <Plus className="size-4" aria-hidden />
                      Add task
                    </Button>
                  </div>
                ) : null}
              </SurfaceCardContent>
            </SurfaceCard>
          </main>

          <aside className="grid gap-6 xl:sticky xl:top-6">
            <SurfaceCard className="border-border/70 rounded-(--radius-card) shadow-card">
              <PanelHeader
                title="Ownership"
                description="One accountable coordinator; source teams still own their milestones."
                className="border-border/60 border-b pb-5"
              />
              <SurfaceCardContent>
                <form
                  method="post"
                  action={routes.new_agent_onboarding_owner(onboarding.user.id)}
                  className="grid gap-4"
                >
                  <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
                  <input
                    type="hidden"
                    name="expected_version"
                    value={onboarding.version}
                  />
                  <SelectField
                    name="owner"
                    label="Onboarding owner"
                    value={owner}
                    onChange={setOwner}
                    placeholder="Unassigned"
                    options={ownerOptions}
                    validation={validation}
                    disabled={!canManage}
                  />
                  <Button type="submit" variant="outline" disabled={!canManage}>
                    <UserRoundCheck className="size-4" aria-hidden />
                    Save owner
                  </Button>
                </form>
              </SurfaceCardContent>
            </SurfaceCard>

            {onboarding.blockers.length ? (
              <SurfaceCard
                state="error"
                className="border-destructive/30 rounded-(--radius-card) bg-destructive/3"
              >
                <PanelHeader title="Activation blockers" />
                <SurfaceCardContent>
                  <ul className="grid gap-3">
                    {onboarding.blockers.map((blocker) => (
                      <li key={blocker.key} className="flex gap-2 text-sm leading-5">
                        <CircleAlert
                          className="text-destructive mt-0.5 size-4 shrink-0"
                          aria-hidden
                        />
                        {blocker.label}
                      </li>
                    ))}
                  </ul>
                </SurfaceCardContent>
              </SurfaceCard>
            ) : (
              <SurfaceCard state="success" className="rounded-(--radius-card)">
                <SurfaceCardContent className="flex gap-3 pt-5">
                  <ShieldCheck className="text-success size-5" aria-hidden />
                  <p className="text-sm font-medium">No activation blockers.</p>
                </SurfaceCardContent>
              </SurfaceCard>
            )}

            {onboarding.eligibleNotices.length ? (
              <SurfaceCard className="border-border/70 rounded-(--radius-card) shadow-card">
                <PanelHeader title="Eligible notices" />
                <SurfaceCardContent className="grid gap-2">
                  {onboarding.eligibleNotices.map((notice) => (
                    <form
                      key={`${notice.source}:${notice.key}`}
                      method="post"
                      action={routes.new_agent_onboarding_notice(onboarding.user.id)}
                    >
                      <input
                        type="hidden"
                        name="csrfmiddlewaretoken"
                        value={csrfToken}
                      />
                      <input type="hidden" name="source" value={notice.source} />
                      <input type="hidden" name="notice" value={notice.key} />
                      <input type="hidden" name="idempotency_key" value={requestId} />
                      <Button
                        type="submit"
                        variant="outline"
                        className="w-full"
                        disabled={!canManage}
                      >
                        {notice.label}
                      </Button>
                    </form>
                  ))}
                </SurfaceCardContent>
              </SurfaceCard>
            ) : null}

            <SurfaceCard state="read-only" className="rounded-(--radius-card)">
              <PanelHeader
                title="Record policy"
                meta={
                  <LockKeyhole className="text-muted-foreground size-4" aria-hidden />
                }
              />
              <SurfaceCardContent className="grid gap-4">
                <p className="text-muted-foreground text-sm leading-6">
                  {privacy.taskPolicy}
                </p>
                <dl className="grid gap-4 border-t pt-4">
                  <ReadOnlyValue label="Last changed">
                    {formatMoment(onboarding.lastChangedAt)}
                  </ReadOnlyValue>
                  <ReadOnlyValue label="Changed by">
                    {onboarding.lastChangedBy ?? "—"}
                  </ReadOnlyValue>
                  <ReadOnlyValue label="General notes">
                    {privacy.notesAllowed ? "Allowed" : "Not collected"}
                  </ReadOnlyValue>
                </dl>
              </SurfaceCardContent>
            </SurfaceCard>

            <SurfaceCard className="border-border/70 rounded-(--radius-card) shadow-card">
              <PanelHeader title="Recent activity" />
              <SurfaceCardContent>
                {activity.length ? (
                  <ol className="grid gap-4">
                    {activity.map((entry) => (
                      <li key={entry.id} className="grid gap-1 border-l pl-3 text-sm">
                        <span className="font-medium">
                          {entry.action.replaceAll(".", " ")}
                        </span>
                        <span className="text-muted-foreground text-xs">
                          {entry.actor} · {formatMoment(entry.occurredAt)}
                        </span>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="text-muted-foreground text-sm">
                    No operational changes have been recorded.
                  </p>
                )}
              </SurfaceCardContent>
            </SurfaceCard>
          </aside>
        </div>
      </div>

      {canManage ? (
        <FormSheet
          open={taskOpen}
          onOpenChange={setTaskOpen}
          title="Add task"
          description="A brief operational instruction for coordinating this onboarding."
          footer={
            <div className="flex items-center justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setTaskOpen(false)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                form="onboarding-task-create-form"
                disabled={taskSubmitting}
                aria-busy={taskSubmitting || undefined}
              >
                {taskSubmitting ? "Adding…" : "Add task"}
              </Button>
            </div>
          }
        >
          <form
            ref={taskFormRef}
            id="onboarding-task-create-form"
            onSubmit={onCreateTaskSubmit}
            className="flex min-h-0 flex-1 flex-col overflow-hidden"
          >
            <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
            <input type="hidden" name="action" value="create" />
            <input type="hidden" name="expected_version" value={onboarding.version} />
            <FormSheetBody>
              <div className="grid gap-5">
                {hasValidationErrors(validation) ? (
                  <FormErrorSummary
                    errors={validation}
                    labels={{ title: "Task", due_on: "Due date" }}
                  />
                ) : null}
                <TextField
                  name="title"
                  label="Task"
                  required
                  maxLength={200}
                  validation={validation}
                  description="A brief operational instruction—no sensitive details."
                />
                <DateField
                  name="due_on"
                  label="Due date"
                  optional
                  validation={validation}
                />
                <FormField>
                  <div className="flex items-start gap-3">
                    <Checkbox id="is_blocking" name="is_blocking" value="1" />
                    <div className="grid gap-1">
                      <FormLabel htmlFor="is_blocking">
                        This task blocks activation
                      </FormLabel>
                      <FormDescription>
                        Use only when the agent cannot safely begin work until it is
                        resolved.
                      </FormDescription>
                    </div>
                  </div>
                </FormField>
              </div>
            </FormSheetBody>
          </form>
        </FormSheet>
      ) : null}
    </PermissionRequired>
  );
}

OnboardingWorkspace.layout = (props: OnboardingWorkspacePageProps) =>
  [
    HubLayout,
    {
      context: {
        title: "Operational onboarding",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "New Agent List", href: routes.admin_new_agents() },
          {
            label: props.onboarding.user.name,
            href: routes.new_agent_onboarding(props.onboarding.user.id),
          },
        ],
        back: { label: "New Agent List", href: routes.admin_new_agents() },
      },
      variant: "wide",
    },
  ] as const;
