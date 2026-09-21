import { Form, Head, Link, router, usePage } from "@inertiajs/react";
import {
  Check,
  CircleAlert,
  Clock3,
  ExternalLink,
  LockKeyhole,
  Mail,
  MapPin,
  Phone,
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
  OnboardingTool,
  OnboardingWorkspaceAction,
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

const TOOL_GROUPS: {
  code: OnboardingTool["group"];
  label: string;
  description: string;
}[] = [
  {
    code: "waiting",
    label: "Waiting",
    description: "No invitation or activation has been recorded yet.",
  },
  {
    code: "invitation_sent",
    label: "Invitation sent",
    description: "The office recorded the invitation; activation is still pending.",
  },
  { code: "ready", label: "Ready", description: "The tool is activated and ready." },
  {
    code: "blocked",
    label: "Blocked",
    description: "An operational issue needs attention.",
  },
  {
    code: "not_applicable",
    label: "Not applicable",
    description: "This catalog tool is not required for the agent.",
  },
];

function ToolSetupActions({
  tool,
  userId,
  version,
  validation,
  editable,
}: {
  tool: OnboardingTool;
  userId: number;
  version: string;
  validation: OnboardingWorkspacePageProps["validation"];
  editable: boolean;
}) {
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState<string | null>(null);

  function run(action: OnboardingWorkspaceAction) {
    if (!action.enabled || submitting) return;
    setSubmitting(action.code);
    router.post(
      routes.new_agent_onboarding_tools(userId),
      {
        expected_version: version,
        tool: tool.key,
        action: action.code,
        reason,
      },
      {
        preserveScroll: true,
        onFinish: () => setSubmitting(null),
      },
    );
  }

  return (
    <article className="border-border/60 grid gap-4 border-b py-5 last:border-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid min-w-0 gap-1">
          <span className="font-semibold">{tool.label}</span>
          {tool.description ? (
            <span className="text-muted-foreground text-sm leading-5">
              {tool.description}
            </span>
          ) : null}
        </div>
        <StatusBadge
          status={{ label: tool.stateLabel, tone: tool.tone }}
          className="shrink-0"
        />
      </div>
      <div className="grid gap-1">
        <span className="text-muted-foreground text-xs">
          {tool.updatedBy
            ? `Updated by ${tool.updatedBy} · ${formatMoment(tool.updatedAt)}`
            : "No operational update yet"}
        </span>
        <span className="text-muted-foreground text-xs">
          {tool.invitationSentAt
            ? `${tool.invitationLabel} · ${formatMoment(tool.invitationSentAt)}`
            : tool.invitationLabel}
        </span>
        {tool.invitationSentAt ? (
          <span className="text-muted-foreground text-xs">{tool.delivery.label}</span>
        ) : null}
      </div>
      {tool.actions.some((action) => action.requiresReason) ? (
        <TextField
          name="reason"
          label={`${tool.label} correction reason`}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="Required when correcting or moving backward"
          validation={validation}
          disabled={!editable}
        />
      ) : null}
      <div className="flex flex-wrap gap-2">
        {tool.actions.map((action) => (
          <Button
            key={action.code}
            type="button"
            variant={action.code === "mark_invitation_sent" ? "default" : "outline"}
            size="sm"
            disabled={
              !editable ||
              !action.enabled ||
              Boolean(submitting) ||
              Boolean(action.requiresReason && !reason.trim())
            }
            title={action.unavailableReason || undefined}
            aria-busy={submitting === action.code || undefined}
            onClick={() => run(action)}
          >
            {submitting === action.code ? "Working…" : action.label}
          </Button>
        ))}
      </div>
      {!tool.actions.some((action) => action.enabled) ? (
        <p className="text-muted-foreground text-xs">
          {tool.actions[0]?.unavailableReason || "No action is currently available."}
        </p>
      ) : null}
    </article>
  );
}

export default function OnboardingWorkspace() {
  const {
    csrfToken,
    requestId,
    user: currentUser,
    onboarding,
    profileSummary,
    confirmedOffice,
    ownerOptions,
    activity,
    validation,
    privacy,
  } = usePage<OnboardingWorkspacePageProps>().props;
  const [owner, setOwner] = useState(onboarding.owner?.id.toString() ?? "");
  const [taskOpen, setTaskOpen] = useState(false);
  const [taskSubmitting, setTaskSubmitting] = useState(false);
  const [contractSubmitting, setContractSubmitting] = useState(false);
  const [recommendedSubmitting, setRecommendedSubmitting] = useState(false);
  const summaryRef = useRef<HTMLDivElement>(null);
  const hasErrors = hasValidationErrors(validation);
  const canManage =
    onboarding.editable &&
    hasPermission(currentUser, { all: ["web.manage_new_agent_onboarding"] });
  const canManageContracts =
    canManage &&
    hasPermission(currentUser, { all: ["contract.manage_agent_contracts"] });
  const canViewContracts = hasPermission(currentUser, {
    any: ["web.view_agent_contracts", "contract.manage_agent_contracts"],
  });
  const canRunContractAction =
    onboarding.contractAction.enabled &&
    (onboarding.contractAction.method === "get"
      ? canViewContracts
      : canManageContracts);
  const percent = onboarding.progress.total
    ? Math.round((onboarding.progress.complete / onboarding.progress.total) * 100)
    : 0;
  const actionVersion = onboarding.journeyVersion ?? onboarding.version;
  const canRunRecommended =
    onboarding.recommendedAction.enabled &&
    (onboarding.recommendedAction.source !== "contract" || canRunContractAction) &&
    (onboarding.recommendedAction.source !== "tool" || canManage) &&
    (onboarding.recommendedAction.source !== "handoff" || canManage);

  function runRecommendedAction() {
    const action = onboarding.recommendedAction;
    if (!canRunRecommended || recommendedSubmitting) return;
    if (action.method === "get" && action.href) {
      router.get(action.href);
      return;
    }
    setRecommendedSubmitting(true);
    const href =
      action.source === "tool"
        ? routes.new_agent_onboarding_tools(onboarding.user.id)
        : action.source === "handoff"
          ? routes.new_agent_onboarding_handoff(onboarding.user.id)
          : routes.new_agent_onboarding_contract(onboarding.user.id);
    router.post(
      href,
      {
        expected_version: actionVersion,
        ...(action.source === "tool"
          ? { tool: action.tool, action: action.code, reason: "" }
          : {}),
      },
      { onFinish: () => setRecommendedSubmitting(false) },
    );
  }

  function runContractAction() {
    const action = onboarding.contractAction;
    if (!canRunContractAction || contractSubmitting) return;
    if (action.method === "get" && action.href) {
      router.get(action.href);
      return;
    }
    setContractSubmitting(true);
    router.post(
      routes.new_agent_onboarding_contract(onboarding.user.id),
      { expected_version: actionVersion },
      {
        preserveScroll: true,
        onFinish: () => setContractSubmitting(false),
      },
    );
  }

  useEffect(() => {
    // While the task sheet is open its own summary has focus; yanking the
    // page behind the overlay would be disorienting.
    if (hasErrors && !taskOpen) summaryRef.current?.focus();
  }, [hasErrors, taskOpen]);

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
              action: "Tool action",
              reason: "Correction reason",
              contract: "Agent contract",
              handoff: "Office handoff",
              expected_version: "Workspace version",
            }}
          />
        </div>

        <section
          aria-labelledby="recommended-action-heading"
          className="border-primary/25 bg-primary/4 grid gap-4 rounded-(--radius-card) border p-5 shadow-card sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"
        >
          <div className="grid gap-1">
            <p className="text-primary text-xs font-semibold tracking-wide uppercase">
              Recommended next action
            </p>
            <h2 id="recommended-action-heading" className="text-lg font-semibold">
              {onboarding.recommendedAction.label}
            </h2>
            <p className="text-muted-foreground text-sm leading-5">
              {onboarding.recommendedAction.description}
            </p>
          </div>
          {canRunRecommended ? (
            <Button
              type="button"
              disabled={recommendedSubmitting}
              aria-busy={recommendedSubmitting || undefined}
              onClick={runRecommendedAction}
            >
              {recommendedSubmitting ? "Working…" : onboarding.recommendedAction.label}
            </Button>
          ) : null}
        </section>

        <div className="grid gap-6 lg:grid-cols-2">
          <SurfaceCard className="border-border/70 rounded-(--radius-card) shadow-card">
            <PanelHeader
              title="Submitted profile"
              description={
                profileSummary.sensitiveFieldsIncluded
                  ? "Profile and permitted administrative fields"
                  : "Sensitive contact and credential fields are withheld by permission"
              }
              className="border-border/60 border-b pb-5"
            />
            <SurfaceCardContent className="grid gap-5">
              <div className="flex items-center gap-4">
                {profileSummary.headshotUrl ? (
                  <img
                    src={profileSummary.headshotUrl}
                    alt={`${onboarding.user.name} headshot`}
                    className="border-border size-20 rounded-2xl border object-cover"
                  />
                ) : (
                  <div className="bg-muted text-muted-foreground grid size-20 place-items-center rounded-2xl text-xs font-medium">
                    No photo
                  </div>
                )}
                <div>
                  <p className="font-semibold">{onboarding.user.name}</p>
                  <p className="text-muted-foreground text-sm">Submitted by agent</p>
                </div>
              </div>
              <dl className="grid gap-4 sm:grid-cols-2">
                {profileSummary.fields.map((field) => (
                  <ReadOnlyValue key={field.key} label={field.label}>
                    {field.value || "—"}
                  </ReadOnlyValue>
                ))}
              </dl>
            </SurfaceCardContent>
          </SurfaceCard>

          <SurfaceCard className="border-border/70 rounded-(--radius-card) shadow-card">
            <PanelHeader
              title="Confirmed office"
              description="The office address controls local resources, ownership, tools, and contract routing."
              className="border-border/60 border-b pb-5"
            />
            <SurfaceCardContent className="grid gap-5">
              {confirmedOffice ? (
                <>
                  <div className="grid gap-1">
                    <p className="font-semibold">{confirmedOffice.office.name}</p>
                    <p className="text-muted-foreground text-sm">
                      {confirmedOffice.office.hierarchy}
                    </p>
                  </div>
                  <div className="flex gap-3 text-sm leading-6">
                    <MapPin
                      className="text-muted-foreground mt-1 size-4 shrink-0"
                      aria-hidden
                    />
                    <div>
                      <p className="font-medium">Office address</p>
                      <p className="text-muted-foreground">
                        {[
                          confirmedOffice.office.streetAddress,
                          [
                            confirmedOffice.office.city,
                            confirmedOffice.office.state,
                            confirmedOffice.office.zipCode,
                          ]
                            .filter(Boolean)
                            .join(" "),
                        ]
                          .filter(Boolean)
                          .join(", ") || "Address not available"}
                      </p>
                    </div>
                  </div>
                  {confirmedOffice.administrator ? (
                    <div className="border-border/60 bg-muted/25 grid gap-3 rounded-xl border p-4">
                      <div>
                        <p className="font-semibold">
                          {confirmedOffice.administrator.name}
                        </p>
                        <p className="text-muted-foreground text-xs">
                          {confirmedOffice.administrator.resolutionLabel}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {confirmedOffice.administrator.phone ? (
                          <Button variant="outline" size="sm" asChild>
                            <a href={`tel:${confirmedOffice.administrator.phone}`}>
                              <Phone className="size-3.5" aria-hidden />
                              Call
                            </a>
                          </Button>
                        ) : null}
                        {confirmedOffice.administrator.email ? (
                          <Button variant="outline" size="sm" asChild>
                            <a href={`mailto:${confirmedOffice.administrator.email}`}>
                              <Mail className="size-3.5" aria-hidden />
                              Email
                            </a>
                          </Button>
                        ) : null}
                      </div>
                    </div>
                  ) : (
                    <p className="text-destructive text-sm">
                      {confirmedOffice.support.message}
                    </p>
                  )}
                  <dl>
                    <ReadOnlyValue label="Onboarding owner">
                      {onboarding.owner?.name ?? "Unassigned"}
                    </ReadOnlyValue>
                  </dl>
                </>
              ) : (
                <p className="text-muted-foreground text-sm">
                  The agent has not confirmed their current office.
                </p>
              )}
            </SurfaceCardContent>
          </SurfaceCard>
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
                description="Actions come from each applicable catalog tool; vendor status is never inferred."
                className="border-border/60 border-b pb-5"
              />
              <SurfaceCardContent className="grid gap-7">
                {TOOL_GROUPS.map((group) => {
                  const tools = onboarding.tools.filter(
                    (tool) => tool.group === group.code,
                  );
                  if (!tools.length) return null;
                  return (
                    <section key={group.code} aria-labelledby={`tools-${group.code}`}>
                      <div className="grid gap-1 border-b pb-3">
                        <h3 id={`tools-${group.code}`} className="font-semibold">
                          {group.label} · {tools.length}
                        </h3>
                        <p className="text-muted-foreground text-xs">
                          {group.description}
                        </p>
                      </div>
                      <div className="grid">
                        {tools.map((tool) => (
                          <ToolSetupActions
                            key={tool.key}
                            tool={tool}
                            userId={onboarding.user.id}
                            version={onboarding.journeyVersion ?? onboarding.version}
                            validation={validation}
                            editable={canManage}
                          />
                        ))}
                      </div>
                    </section>
                  );
                })}
              </SurfaceCardContent>
            </SurfaceCard>

            <SurfaceCard className="border-border/70 rounded-(--radius-card) shadow-card">
              <PanelHeader
                title="Agent contract"
                description="Status and actions come directly from the contract domain."
                className="border-border/60 border-b pb-5"
                meta={<StatusBadge status={onboarding.contract} />}
              />
              <SurfaceCardContent className="grid gap-4">
                <p className="text-muted-foreground text-sm leading-6">
                  Contract generation, issuance, signing, and activation remain in the
                  contract workspace. This onboarding record never carries a manual
                  contract status.
                </p>
                <div>
                  <Button
                    type="button"
                    variant="outline"
                    disabled={!canRunContractAction || contractSubmitting}
                    aria-busy={contractSubmitting || undefined}
                    title={onboarding.contractAction.unavailableReason || undefined}
                    onClick={runContractAction}
                  >
                    {contractSubmitting ? "Working…" : onboarding.contractAction.label}
                  </Button>
                </div>
                {!onboarding.contractAction.enabled &&
                onboarding.contractAction.unavailableReason ? (
                  <p className="text-muted-foreground text-xs">
                    {onboarding.contractAction.unavailableReason}
                  </p>
                ) : null}
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
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={!canManage}
                          onClick={() =>
                            router.post(
                              routes.new_agent_onboarding_tasks(onboarding.user.id),
                              {
                                action: "resolve",
                                task: task.id,
                                expected_version: actionVersion,
                              },
                              { preserveScroll: true },
                            )
                          }
                        >
                          <Check className="size-3.5" aria-hidden />
                          Resolve
                        </Button>
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
                <div className="grid gap-4">
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
                  <Button
                    type="button"
                    variant="outline"
                    disabled={!canManage}
                    onClick={() =>
                      router.post(
                        routes.new_agent_onboarding_owner(onboarding.user.id),
                        { owner, expected_version: actionVersion },
                        { preserveScroll: true },
                      )
                    }
                  >
                    <UserRoundCheck className="size-4" aria-hidden />
                    Save owner
                  </Button>
                </div>
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
                    <div key={`${notice.source}:${notice.key}`}>
                      <Button
                        type="button"
                        variant="outline"
                        className="w-full"
                        disabled={!canManage}
                        onClick={() =>
                          router.post(
                            routes.new_agent_onboarding_notice(onboarding.user.id),
                            {
                              source: notice.source,
                              notice: notice.key,
                              idempotency_key: requestId,
                              expected_version: actionVersion,
                            },
                            { preserveScroll: true },
                          )
                        }
                      >
                        {notice.label}
                      </Button>
                    </div>
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
          <Form
            id="onboarding-task-create-form"
            action={routes.new_agent_onboarding_tasks(onboarding.user.id)}
            method="post"
            disableWhileProcessing
            resetOnSuccess
            onStart={() => setTaskSubmitting(true)}
            onFinish={() => setTaskSubmitting(false)}
            onSuccess={() => setTaskOpen(false)}
            className="flex min-h-0 flex-1 flex-col overflow-hidden"
          >
            <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
            <input type="hidden" name="action" value="create" />
            <input type="hidden" name="expected_version" value={actionVersion} />
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
          </Form>
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
