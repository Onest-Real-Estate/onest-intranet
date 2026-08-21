import { Head, Link, usePage } from "@inertiajs/react";
import { ArrowRight, History, Lock, ShieldAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  type AccessChange,
  AccessChangeDialog,
} from "@/components/administration/AccessChangeDialog";
import { AccountAccessPanel } from "@/components/administration/AccountAccessPanel";
import { RoleAssignmentsPanel } from "@/components/administration/RoleAssignmentsPanel";
import {
  DateField,
  FormActionBar,
  FormDescription,
  FormErrorSummary,
  FormField,
  FormLabel,
  PageHeader,
  PanelHeader,
  ReadOnlyValue,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
  Timeline,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { SelectField, TextField } from "@/components/profile/profile-fields";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { hasPermission } from "@/lib/permissions";
import { routes } from "@/lib/routes";
import { hasValidationErrors } from "@/lib/validation";
import type { UserAdministrationPageProps } from "@/types";

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

/** Django field name → the wording used in the error summary. */
const ERROR_LABELS: Record<string, string> = {
  office: "Office",
  agent_status: "Agent status",
  start_date: "Start date",
  agent_identifier: "Agent ID",
  license_verification_state: "License verification",
  license_verification_note: "Verification note",
  internal_notes: "Operational notes",
  role: "Role",
  scope_type: "Scope",
  scope_office: "Office or region",
  starts_at: "Effective from",
  ends_at: "Effective until",
  business_reason: "Business reason",
};

function formatMoment(value: string | null): string {
  if (!value) return "Never";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "Never" : parsed.toLocaleString();
}

/**
 * One user's broker-controlled record.
 *
 * The page is deliberately not the profile editor with extra fields bolted on:
 * it posts to its own endpoint, it never carries a self-service field, and the
 * two things that move somebody's access — their office and their status —
 * cannot be submitted without first being confirmed against what they do.
 */
export default function UserAdministration() {
  const { csrfToken, administration, validation, user } =
    usePage<UserAdministrationPageProps>().props;
  const {
    subject,
    values,
    version,
    fields,
    license,
    contractStatus,
    accountState,
    provenance,
    history,
    assignments,
    effectiveAccess,
    options,
    editable,
  } = administration;

  const [officeId, setOfficeId] = useState(values.officeId);
  const [agentStatus, setAgentStatus] = useState(values.agentStatus);
  const [verificationState, setVerificationState] = useState(
    values.licenseVerificationState,
  );
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const summaryRef = useRef<HTMLDivElement>(null);
  const hasErrors = hasValidationErrors(validation);

  // A 422 or a 409 arrives as a fresh document, so move focus to the summary
  // rather than leaving it at the top of an apparently unchanged page.
  useEffect(() => {
    if (hasErrors) {
      summaryRef.current?.focus();
    }
  }, [hasErrors]);

  const officeLabel = (id: string) =>
    options.offices.find((office) => String(office.id) === id)?.pathLabel ??
    subject.office?.pathLabel ??
    "—";
  const statusLabel = (value: string) =>
    options.agentStatuses.find((status) => status.value === value)?.label ?? value;

  // The server decides *which* fields need confirming; the page owns the
  // wording for each. A field the server stops calling high-impact stops
  // prompting here without a second edit.
  const confirms = (field: string) => administration.highImpactFields.includes(field);
  const pendingChanges: AccessChange[] = [];
  if (confirms("office") && officeId !== values.officeId) {
    pendingChanges.push({
      label: "Office",
      from: officeLabel(values.officeId),
      to: officeLabel(officeId),
      impact:
        "Everything scoped to their office moves with them, and their Agent assignment in the old office is retired.",
    });
  }
  if (confirms("agent_status") && agentStatus !== values.agentStatus) {
    pendingChanges.push({
      label: "Agent status",
      from: statusLabel(values.agentStatus),
      to: statusLabel(agentStatus),
      impact:
        agentStatus === "departed" || agentStatus === "suspended"
          ? "Their remaining role assignments may then be revoked, which removes their access entirely."
          : "Recorded on their profile and in the agent directory.",
    });
  }

  const fieldSpec = (key: string) => fields.find((field) => field.key === key);
  const readOnly = !editable.administration;

  return (
    <div className="grid gap-10">
      <Head title={`Administer ${subject.displayName}`} />
      <PageHeader
        title={
          <span className="flex min-w-0 items-center gap-3">
            <Avatar className="ring-border size-11 ring-1" aria-hidden>
              {subject.headshotUrl ? (
                <AvatarImage src={subject.headshotUrl} alt="" />
              ) : null}
              <AvatarFallback className="bg-secondary text-secondary-foreground text-sm font-semibold">
                {initials(subject.displayName)}
              </AvatarFallback>
            </Avatar>
            <span className="min-w-0 truncate">{subject.displayName}</span>
          </span>
        }
        description={`${subject.email} · ${subject.office?.pathLabel ?? "No office"}`}
        meta={
          <span className="flex items-center gap-2">
            <StatusBadge
              status={{
                label: statusLabel(values.agentStatus),
                tone:
                  options.agentStatuses.find(
                    (status) => status.value === values.agentStatus,
                  )?.tone ?? "neutral",
              }}
            />
          </span>
        }
      />

      {subject.isSelf ? (
        <SurfaceCard state="read-only" className="border-warning/25 bg-warning/8">
          <SurfaceCardContent className="flex items-start gap-3">
            <ShieldAlert
              className="text-warning-ink mt-0.5 size-5 shrink-0"
              aria-hidden
            />
            <p className="text-sm">
              This is your own record. Nobody administers their own roles, office, or
              status — ask another administrator to make the change.
            </p>
          </SurfaceCardContent>
        </SurfaceCard>
      ) : null}

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_20rem] xl:gap-x-8">
        <div className="grid content-start gap-6">
          <form
            ref={formRef}
            method="post"
            action={routes.user_administration_submit(subject.id)}
            className="grid gap-6"
            onSubmit={(event) => {
              if (pendingChanges.length > 0 && !submitting) {
                event.preventDefault();
                setConfirming(true);
                return;
              }
              setSubmitting(true);
            }}
          >
            <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
            <input type="hidden" name="expected_version" value={version} />

            <div ref={summaryRef} tabIndex={-1} className="outline-none">
              <FormErrorSummary errors={validation} labels={ERROR_LABELS} />
            </div>

            <SurfaceCard>
              <PanelHeader
                divided
                title="Placement and status"
                description="Changing either of these moves what this person can reach."
              />
              <SurfaceCardContent className="grid gap-4 sm:grid-cols-2">
                <SelectField
                  name="office"
                  label="Office"
                  required
                  disabled={readOnly}
                  value={officeId}
                  onChange={setOfficeId}
                  placeholder="Select an office"
                  options={options.offices.map((office) => ({
                    value: String(office.id),
                    label: office.pathLabel,
                  }))}
                  validation={validation}
                  description={fieldSpec("office")?.description}
                />
                <SelectField
                  name="agent_status"
                  label="Agent status"
                  required
                  disabled={readOnly}
                  value={agentStatus}
                  onChange={setAgentStatus}
                  placeholder="Select a status"
                  options={options.agentStatuses.map((status) => ({
                    value: status.value,
                    label: status.label,
                  }))}
                  validation={validation}
                  description={fieldSpec("agent_status")?.description}
                />
                <DateField
                  name="start_date"
                  label="Start date"
                  optional
                  disabled={readOnly}
                  defaultValue={values.startDate}
                  validation={validation}
                  description={fieldSpec("start_date")?.description}
                />
                <TextField
                  name="agent_identifier"
                  label="Agent ID"
                  optional
                  disabled={readOnly}
                  defaultValue={values.agentIdentifier}
                  validation={validation}
                  description={fieldSpec("agent_identifier")?.description}
                />
              </SurfaceCardContent>
            </SurfaceCard>

            <SurfaceCard>
              <PanelHeader
                divided
                title="License verification"
                description="What the agent recorded, and what the brokerage checked."
              />
              <SurfaceCardContent className="grid gap-4">
                <dl className="bg-muted/40 border-border/60 grid gap-4 rounded-lg border p-4 sm:grid-cols-3">
                  <ReadOnlyValue label="License number">
                    {license.number || "Not recorded"}
                  </ReadOnlyValue>
                  <ReadOnlyValue label="State">{license.state || "—"}</ReadOnlyValue>
                  <ReadOnlyValue label="Expires">
                    {license.expiresOn ?? "—"}
                  </ReadOnlyValue>
                </dl>
                <div className="grid gap-4 sm:grid-cols-2">
                  <SelectField
                    name="license_verification_state"
                    label="Verification"
                    required
                    disabled={readOnly}
                    value={verificationState}
                    onChange={setVerificationState}
                    placeholder="Select a state"
                    options={options.licenseVerificationStates.map((state) => ({
                      value: state.value,
                      label: state.label,
                    }))}
                    validation={validation}
                    description={fieldSpec("license_verification_state")?.description}
                  />
                  <TextField
                    name="license_verification_note"
                    label="Verification note"
                    optional
                    disabled={readOnly}
                    defaultValue={values.licenseVerificationNote}
                    validation={validation}
                    description={fieldSpec("license_verification_note")?.description}
                  />
                </div>
                {license.verification.verifiedAt ? (
                  <p className="text-muted-foreground text-sm">
                    Last checked {formatMoment(license.verification.verifiedAt)} by{" "}
                    {license.verification.verifiedBy ?? "an administrator"}.
                  </p>
                ) : null}
              </SurfaceCardContent>
            </SurfaceCard>

            {values.internalNotes === undefined ? null : (
              <SurfaceCard>
                <PanelHeader
                  divided
                  title="Operational notes"
                  description="Internal to administrators. Never shown to this person, and never written into the audit trail as text."
                  meta={
                    <span className="text-muted-foreground flex items-center gap-1 text-xs font-medium">
                      <Lock className="size-3.5" aria-hidden />
                      Private
                    </span>
                  }
                />
                <SurfaceCardContent>
                  <FormField>
                    <FormLabel htmlFor="internal_notes" optional>
                      Notes
                    </FormLabel>
                    <Textarea
                      id="internal_notes"
                      name="internal_notes"
                      rows={5}
                      disabled={readOnly}
                      defaultValue={values.internalNotes}
                      maxLength={4000}
                      className="min-h-32 resize-y"
                    />
                    <FormDescription>
                      Keep these factual and operational. The audit trail records only
                      that they changed.
                    </FormDescription>
                  </FormField>
                </SurfaceCardContent>
              </SurfaceCard>
            )}

            <FormActionBar
              status={
                readOnly
                  ? "You may read this record but not change it."
                  : pendingChanges.length > 0
                    ? "Saving will ask you to confirm the access changes first."
                    : "Changes are recorded in the audit trail."
              }
            >
              <Button type="submit" disabled={readOnly || submitting}>
                {submitting ? "Saving…" : "Save administrative record"}
              </Button>
            </FormActionBar>
          </form>

          <RoleAssignmentsPanel
            userId={subject.id}
            csrfToken={csrfToken}
            assignments={assignments}
            roleOptions={options.roles}
            officeOptions={options.offices}
            validation={validation}
            editable={editable.roleAssignments}
            manageHref={
              hasPermission(user, { all: ["web.assign_user_roles"] }) && !subject.isSelf
                ? routes.admin_assign_roles_user(subject.id)
                : null
            }
          />
        </div>

        <aside className="grid content-start gap-6 xl:sticky xl:top-22">
          <AccountAccessPanel
            userId={subject.id}
            userName={subject.preferredDisplayName || subject.displayName}
            csrfToken={csrfToken}
            version={version}
            state={accountState}
          />

          {administration.onboardingState ? (
            <SurfaceCard>
              <PanelHeader
                divided
                title="Onboarding"
                description="Current source-derived activation state."
                meta={<StatusBadge status={administration.onboardingState.overall} />}
              />
              <SurfaceCardContent className="grid gap-4">
                <p className="text-muted-foreground text-sm">
                  {administration.onboardingState.progress.complete} of{" "}
                  {administration.onboardingState.progress.total} milestones complete
                  {administration.onboardingState.blockers.length
                    ? ` · ${administration.onboardingState.blockers.length} blockers`
                    : ""}
                </p>
                <dl className="grid gap-4 sm:grid-cols-2">
                  <ReadOnlyValue label="Training">
                    <StatusBadge status={administration.onboardingState.training} />
                  </ReadOnlyValue>
                  {administration.onboardingState.contract ? (
                    <ReadOnlyValue label="Contract">
                      <StatusBadge status={administration.onboardingState.contract} />
                    </ReadOnlyValue>
                  ) : null}
                </dl>
                <Button variant="outline" size="sm" asChild>
                  <Link href={administration.onboardingState.href}>
                    Open onboarding workspace
                    <ArrowRight className="size-3.5" aria-hidden />
                  </Link>
                </Button>
              </SurfaceCardContent>
            </SurfaceCard>
          ) : null}

          <SurfaceCard>
            <PanelHeader
              divided
              title="Effective access"
              description="What this record resolves to right now."
            />
            <SurfaceCardContent>
              <dl className="grid gap-4">
                <ReadOnlyValue label="Roles">
                  {effectiveAccess.roles.join(", ") || "None"}
                </ReadOnlyValue>
                <ReadOnlyValue label="Scope">
                  {effectiveAccess.scopeLabel}
                </ReadOnlyValue>
                <ReadOnlyValue label="Live assignments">
                  {effectiveAccess.liveAssignments}
                </ReadOnlyValue>
                {contractStatus ? (
                  <ReadOnlyValue label="Contract status">
                    <StatusBadge
                      status={{
                        label: contractStatus.label,
                        tone: contractStatus.tone,
                      }}
                    />
                    <p className="text-muted-foreground mt-1 text-xs">
                      {contractStatus.available
                        ? `Owned by the ${contractStatus.source} module.`
                        : contractStatus.reason}
                    </p>
                  </ReadOnlyValue>
                ) : null}
              </dl>
            </SurfaceCardContent>
          </SurfaceCard>

          <SurfaceCard>
            <PanelHeader
              divided
              title="Recent activity"
              meta={
                <span className="text-muted-foreground flex items-center gap-1 text-xs font-medium">
                  <History className="size-3.5" aria-hidden />
                  Audited
                </span>
              }
            />
            <SurfaceCardContent className="grid gap-4">
              <dl className="grid gap-4">
                <ReadOnlyValue label="When">
                  {formatMoment(provenance.lastChangedAt)}
                </ReadOnlyValue>
                <ReadOnlyValue label="By">
                  {provenance.lastChangedBy ?? "—"}
                </ReadOnlyValue>
              </dl>
              {history.length > 0 ? (
                <Timeline
                  className="border-t pt-4"
                  items={history.map((entry) => ({
                    id: entry.id,
                    title: entry.label,
                    meta: formatMoment(entry.occurredAt),
                    description:
                      entry.actor +
                      (entry.reason
                        ? ` · ${entry.reason}`
                        : entry.fields.length
                          ? ` · ${entry.fields.join(", ")}`
                          : ""),
                  }))}
                />
              ) : (
                <p className="text-muted-foreground border-t pt-4 text-sm">
                  Nothing has been changed on this record yet.
                </p>
              )}
            </SurfaceCardContent>
          </SurfaceCard>
        </aside>
      </div>

      <AccessChangeDialog
        open={confirming}
        onOpenChange={setConfirming}
        title="Confirm the access change"
        description={`These changes take effect for ${subject.displayName} on their next request.`}
        changes={pendingChanges}
        confirmLabel="Apply changes"
        submitting={submitting}
        onConfirm={() => {
          setSubmitting(true);
          setConfirming(false);
          formRef.current?.submit();
        }}
      />
    </div>
  );
}

UserAdministration.layout = (props: UserAdministrationPageProps) =>
  [
    HubLayout,
    {
      context: {
        title: "User administration",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Users", href: routes.admin_users() },
          {
            label: props.administration.subject.displayName,
            href: routes.user_administration(props.administration.subject.id),
          },
        ],
      },
      variant: "standard",
    },
  ] as const;
