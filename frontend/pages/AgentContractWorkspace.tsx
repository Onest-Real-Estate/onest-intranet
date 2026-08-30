import { Head, router, usePage } from "@inertiajs/react";
import { useMemo, useState } from "react";
import { AccessChangeDialog } from "@/components/administration/AccessChangeDialog";
import { CommissionCalculator } from "@/components/administration/CommissionCalculator";
import { ContractPayeeSearch } from "@/components/ContractPayeeSearch";
import {
  NativeSelect,
  PageHeader,
  PanelHeader,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useValidationToasts } from "@/hooks/use-validation-toasts";
import { toFormData } from "@/lib/form-data";
import { routes } from "@/lib/routes";
import type {
  AgentContractPayeeSummary,
  AgentContractWorkspacePageProps,
} from "@/types";
import type { StatusTone } from "@/types/design-system";

const ACCESS = {
  any: ["web.view_agent_contracts", "contract.manage_agent_contracts"],
};

/** Matches ``CommissionBasis.FIXED_ONLY`` — percent is invalid for this basis. */
const FIXED_ONLY_BASIS = "fixed_only";

/** High-impact lifecycle moves that require an AccessChangeDialog confirm. */
type ConfirmLifecycleAction = "issue" | "activate" | "supersede" | "terminate";

const CONFIRM_LIFECYCLE: Record<
  ConfirmLifecycleAction,
  {
    title: string;
    description: string;
    confirmLabel: string;
    toLabel: string;
    impact: string;
  }
> = {
  issue: {
    title: "Issue this contract?",
    description:
      "Freezes party, office, terms, template version, and calculation rule version, then queues PDF generation and marks the contract sent.",
    confirmLabel: "Confirm issue",
    toLabel: "Sent to agent",
    impact: "Agent can review the issued agreement after PDF generation.",
  },
  activate: {
    title: "Activate this contract?",
    description:
      "Marks the signed agreement as the agent's active brokerage contract and supersedes any prior active contract for the same recipient.",
    confirmLabel: "Confirm activate",
    toLabel: "Active",
    impact: "Onboarding and operations treat this version as the live agreement.",
  },
  supersede: {
    title: "Supersede this contract?",
    description:
      "Ends this version without terminating the agent relationship. Use when a replacement agreement will take its place.",
    confirmLabel: "Confirm supersede",
    toLabel: "Superseded",
    impact: "This version leaves the active pipeline and cannot be reactivated.",
  },
  terminate: {
    title: "Terminate this contract?",
    description:
      "Ends this agreement. This is a terminal status and cannot be undone from the workspace.",
    confirmLabel: "Confirm terminate",
    toLabel: "Terminated",
    impact: "The agent no longer has this version as a live or pending agreement.",
  },
};

function toTone(raw: string): StatusTone {
  if (raw === "danger") return "destructive";
  if (
    raw === "neutral" ||
    raw === "info" ||
    raw === "success" ||
    raw === "warning" ||
    raw === "destructive"
  ) {
    return raw;
  }
  return "neutral";
}

function field(commission: Record<string, unknown> | undefined, key: string): string {
  const value = commission?.[key];
  return value == null ? "" : String(value);
}

function nested(
  commission: Record<string, unknown> | undefined,
  block: string,
  key: string,
): string {
  const group = commission?.[block];
  if (!group || typeof group !== "object") return "";
  const value = (group as Record<string, unknown>)[key];
  return value == null ? "" : String(value);
}

function payeeSummary(
  commission: Record<string, unknown> | undefined,
  block: string,
): AgentContractPayeeSummary | null {
  const group = commission?.[block];
  if (!group || typeof group !== "object") return null;
  const record = group as Record<string, unknown>;
  const payee = record.payee;
  if (payee && typeof payee === "object") {
    const row = payee as Record<string, unknown>;
    if (row.id == null) return null;
    return {
      id: Number(row.id),
      name: String(row.name ?? ""),
      email: String(row.email ?? ""),
      officeId: row.officeId == null ? null : Number(row.officeId),
      officeName: String(row.officeName ?? ""),
    };
  }
  return null;
}

export default function AgentContractWorkspace() {
  const {
    contract,
    expectedVersion,
    capabilities,
    allowedActions,
    recipient,
    office,
    templateOptions,
    commissionBasisOptions,
    commercialPreview,
    errors,
    agreementPreview,
    generatedPdfUrl,
    csrfToken,
  } = usePage<AgentContractWorkspacePageProps>().props;
  const commission = contract.commission as Record<string, unknown> | undefined;
  const [confirmAction, setConfirmAction] = useState<ConfirmLifecycleAction | null>(
    null,
  );
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const canEdit = capabilities.canManage && contract.status === "draft";
  useValidationToasts(errors);
  const confirmCopy = confirmAction ? CONFIRM_LIFECYCLE[confirmAction] : null;
  const [mentorBasis, setMentorBasis] = useState(() =>
    nested(commission, "mentor", "basis"),
  );
  const [mentorPercent, setMentorPercent] = useState(() =>
    nested(commission, "mentor", "percent"),
  );
  const [mentorFixed, setMentorFixed] = useState(() =>
    nested(commission, "mentor", "fixedAmount"),
  );
  const [referralBasis, setReferralBasis] = useState(() =>
    nested(commission, "referral", "basis"),
  );
  const [referralPercent, setReferralPercent] = useState(() =>
    nested(commission, "referral", "percent"),
  );
  const [referralFixed, setReferralFixed] = useState(() =>
    nested(commission, "referral", "fixedAmount"),
  );
  const mentorPayee = payeeSummary(commission, "mentor");
  const referralPayee = payeeSummary(commission, "referral");
  const mentorIsFixedOnly = mentorBasis === FIXED_ONLY_BASIS;
  const referralIsFixedOnly = referralBasis === FIXED_ONLY_BASIS;
  const mentorHasAmount =
    mentorPercent.trim().length > 0 || mentorFixed.trim().length > 0;
  const referralHasAmount =
    referralPercent.trim().length > 0 || referralFixed.trim().length > 0;
  const showMentorPayee = Boolean(mentorBasis && mentorHasAmount);
  const showReferralPayee = Boolean(referralBasis && referralHasAmount);

  function onMentorBasisChange(value: string) {
    const next = value === "__none__" ? "" : value;
    setMentorBasis(next);
    if (next === FIXED_ONLY_BASIS) {
      setMentorPercent("");
    }
  }

  function onReferralBasisChange(value: string) {
    const next = value === "__none__" ? "" : value;
    setReferralBasis(next);
    if (next === FIXED_ONLY_BASIS) {
      setReferralPercent("");
    }
  }

  const officeName = useMemo(
    () => String((office as { name?: string }).name ?? ""),
    [office],
  );

  function postLifecycle(action: string, confirmed = false) {
    router.post(
      routes.agent_contract_lifecycle(contract.publicId),
      // FormData so Django request.POST receives the action (JSON bodies do not).
      toFormData({
        action,
        expected_version: expectedVersion,
        confirmed: confirmed ? "1" : "",
        idempotency_key: idempotencyKey,
      }),
      { preserveScroll: true },
    );
  }

  return (
    <PermissionRequired permission={ACCESS}>
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <Head title={`Contract · ${recipient.name}`} />
        <div className="grid gap-6">
          <PageHeader
            title={recipient.name}
            description={`${recipient.email} · ${officeName}`}
            meta={
              <StatusBadge
                status={{
                  label: contract.statusLabel,
                  tone: toTone(contract.statusTone),
                }}
              />
            }
          />

          <form
            method="post"
            action={routes.agent_contract_update(contract.publicId)}
            className="grid gap-6"
            onSubmit={(event) => {
              event.preventDefault();
              const form = event.currentTarget;
              router.post(form.action, new FormData(form), {
                preserveScroll: true,
              });
            }}
          >
            <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
            <input type="hidden" name="expected_version" value={expectedVersion} />
            <input
              type="hidden"
              name="office_id"
              value={String((office as { officeId?: number }).officeId ?? "")}
            />

            <SurfaceCard>
              <PanelHeader
                title="Party and office"
                description="Derived from the agent profile. Snapshots refresh on save."
              />
              <SurfaceCardContent className="grid gap-2 text-sm">
                <p>
                  <span className="text-muted-foreground">License:</span>{" "}
                  {recipient.licenseState || "—"}
                </p>
                <p>
                  <span className="text-muted-foreground">Office:</span> {officeName}
                </p>
              </SurfaceCardContent>
            </SurfaceCard>

            <SurfaceCard>
              <PanelHeader title="Template and dates" />
              <SurfaceCardContent className="grid gap-4 md:grid-cols-2">
                <div className="grid gap-2 md:col-span-2">
                  <Label htmlFor="template_version_id">Template version</Label>
                  <NativeSelect
                    id="template_version_id"
                    name="template_version_id"
                    defaultValue={contract.templateVersionId ?? ""}
                    disabled={!canEdit}
                    required
                  >
                    <option value="">Select template</option>
                    {templateOptions.map((option) => (
                      <option key={option.id} value={option.id}>
                        {option.templateName} ({option.versionLabel})
                      </option>
                    ))}
                  </NativeSelect>
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="effective_on">Effective on</Label>
                  <Input
                    id="effective_on"
                    name="effective_on"
                    type="date"
                    defaultValue={contract.effectiveOn}
                    disabled={!canEdit}
                    required
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="expires_on">Expires on</Label>
                  <Input
                    id="expires_on"
                    name="expires_on"
                    type="date"
                    defaultValue={contract.expiresOn ?? ""}
                    disabled={!canEdit}
                  />
                </div>
              </SurfaceCardContent>
            </SurfaceCard>

            {capabilities.canViewCommission ? (
              <>
                <SurfaceCard>
                  <PanelHeader
                    title="Splits and fees"
                    description="Percentages use unit percent (0–100). Money is USD."
                  />
                  <SurfaceCardContent className="grid gap-4 md:grid-cols-2">
                    <div className="grid gap-2">
                      <Label htmlFor="agent_split_percent">Agent split (%)</Label>
                      <Input
                        id="agent_split_percent"
                        name="agent_split_percent"
                        defaultValue={field(commission, "agentSplitPercent")}
                        disabled={!canEdit}
                        inputMode="decimal"
                      />
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="office_split_percent">Office split (%)</Label>
                      <Input
                        id="office_split_percent"
                        name="office_split_percent"
                        defaultValue={field(commission, "officeSplitPercent")}
                        disabled={!canEdit}
                        inputMode="decimal"
                      />
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="transaction_fee_amount">
                        Transaction fee (USD)
                      </Label>
                      <Input
                        id="transaction_fee_amount"
                        name="transaction_fee_amount"
                        defaultValue={field(commission, "transactionFeeAmount")}
                        disabled={!canEdit}
                        inputMode="decimal"
                      />
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="annual_cap_amount">Annual cap (USD)</Label>
                      <Input
                        id="annual_cap_amount"
                        name="annual_cap_amount"
                        defaultValue={field(commission, "annualCapAmount")}
                        disabled={!canEdit}
                        inputMode="decimal"
                      />
                    </div>
                  </SurfaceCardContent>
                </SurfaceCard>

                <SurfaceCard>
                  <PanelHeader
                    title="Mentor terms"
                    description="Pick a basis first. Fixed-only hides percent; other bases use percent (optional fixed add-on)."
                  />
                  <SurfaceCardContent className="grid gap-4 md:grid-cols-2">
                    <div className="grid gap-2 md:col-span-2">
                      <Label htmlFor="mentor_basis">Mentor basis</Label>
                      <input type="hidden" name="mentor_basis" value={mentorBasis} />
                      <Select
                        value={mentorBasis || "__none__"}
                        onValueChange={onMentorBasisChange}
                        disabled={!canEdit}
                      >
                        <SelectTrigger id="mentor_basis">
                          <SelectValue placeholder="Select calculation basis" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__none__">None</SelectItem>
                          {commissionBasisOptions.map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {option.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    {mentorBasis && !mentorIsFixedOnly ? (
                      <div className="grid gap-2">
                        <Label htmlFor="mentor_percent">Mentor percent (%)</Label>
                        <Input
                          id="mentor_percent"
                          name="mentor_percent"
                          value={mentorPercent}
                          onChange={(event) => setMentorPercent(event.target.value)}
                          disabled={!canEdit}
                          inputMode="decimal"
                        />
                      </div>
                    ) : (
                      <input type="hidden" name="mentor_percent" value="" />
                    )}
                    {mentorBasis ? (
                      <div className="grid gap-2">
                        <Label htmlFor="mentor_fixed_amount">
                          {mentorIsFixedOnly
                            ? "Mentor fixed (USD)"
                            : "Mentor fixed add-on (USD)"}
                        </Label>
                        <Input
                          id="mentor_fixed_amount"
                          name="mentor_fixed_amount"
                          value={mentorFixed}
                          onChange={(event) => setMentorFixed(event.target.value)}
                          disabled={!canEdit}
                          inputMode="decimal"
                          required={mentorIsFixedOnly && canEdit}
                        />
                      </div>
                    ) : (
                      <input type="hidden" name="mentor_fixed_amount" value="" />
                    )}
                    {!mentorBasis ? (
                      <p className="text-muted-foreground text-sm md:col-span-2">
                        Choose a calculation basis to enter amounts and pick a payee.
                      </p>
                    ) : !mentorHasAmount ? (
                      <p className="text-muted-foreground text-sm md:col-span-2">
                        Enter a percent or fixed amount to choose a mentor payee.
                      </p>
                    ) : null}
                    {showMentorPayee ? (
                      <div className="md:col-span-2">
                        <ContractPayeeSearch
                          id="mentor_payee_search"
                          name="mentor_payee_id"
                          label="Mentor payee"
                          disabled={!canEdit}
                          initialPayee={mentorPayee}
                        />
                      </div>
                    ) : (
                      <input type="hidden" name="mentor_payee_id" value="" />
                    )}
                  </SurfaceCardContent>
                </SurfaceCard>

                <SurfaceCard>
                  <PanelHeader
                    title="Referral terms"
                    description="Same as mentor: pick a basis, enter an amount, then choose a payee. Calculated in parallel."
                  />
                  <SurfaceCardContent className="grid gap-4 md:grid-cols-2">
                    <div className="grid gap-2 md:col-span-2">
                      <Label htmlFor="referral_basis">Referral basis</Label>
                      <input
                        type="hidden"
                        name="referral_basis"
                        value={referralBasis}
                      />
                      <Select
                        value={referralBasis || "__none__"}
                        onValueChange={onReferralBasisChange}
                        disabled={!canEdit}
                      >
                        <SelectTrigger id="referral_basis">
                          <SelectValue placeholder="Select calculation basis" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__none__">None</SelectItem>
                          {commissionBasisOptions.map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {option.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    {referralBasis && !referralIsFixedOnly ? (
                      <div className="grid gap-2">
                        <Label htmlFor="referral_percent">Referral percent (%)</Label>
                        <Input
                          id="referral_percent"
                          name="referral_percent"
                          value={referralPercent}
                          onChange={(event) => setReferralPercent(event.target.value)}
                          disabled={!canEdit}
                          inputMode="decimal"
                        />
                      </div>
                    ) : (
                      <input type="hidden" name="referral_percent" value="" />
                    )}
                    {referralBasis ? (
                      <div className="grid gap-2">
                        <Label htmlFor="referral_fixed_amount">
                          {referralIsFixedOnly
                            ? "Referral fixed (USD)"
                            : "Referral fixed add-on (USD)"}
                        </Label>
                        <Input
                          id="referral_fixed_amount"
                          name="referral_fixed_amount"
                          value={referralFixed}
                          onChange={(event) => setReferralFixed(event.target.value)}
                          disabled={!canEdit}
                          inputMode="decimal"
                          required={referralIsFixedOnly && canEdit}
                        />
                      </div>
                    ) : (
                      <input type="hidden" name="referral_fixed_amount" value="" />
                    )}
                    {!referralBasis ? (
                      <p className="text-muted-foreground text-sm md:col-span-2">
                        Choose a calculation basis to enter amounts and pick a payee.
                      </p>
                    ) : !referralHasAmount ? (
                      <p className="text-muted-foreground text-sm md:col-span-2">
                        Enter a percent or fixed amount to choose a referral payee.
                      </p>
                    ) : null}
                    {showReferralPayee ? (
                      <div className="md:col-span-2">
                        <ContractPayeeSearch
                          id="referral_payee_search"
                          name="referral_payee_id"
                          label="Referral payee"
                          disabled={!canEdit}
                          initialPayee={referralPayee}
                        />
                      </div>
                    ) : (
                      <input type="hidden" name="referral_payee_id" value="" />
                    )}
                  </SurfaceCardContent>
                </SurfaceCard>
              </>
            ) : null}

            <SurfaceCard>
              <PanelHeader title="Addenda and notes" />
              <SurfaceCardContent className="grid gap-4">
                <div className="grid gap-2">
                  <Label htmlFor="special_arrangements">Special arrangements</Label>
                  <Textarea
                    id="special_arrangements"
                    name="special_arrangements"
                    rows={3}
                    defaultValue={field(commission, "specialArrangements")}
                    disabled={!canEdit}
                  />
                </div>
                {capabilities.canViewNotes ? (
                  <div className="grid gap-2">
                    <Label htmlFor="internal_notes">Internal notes</Label>
                    <Textarea
                      id="internal_notes"
                      name="internal_notes"
                      rows={3}
                      defaultValue={contract.internalNotes ?? ""}
                      disabled={!canEdit}
                    />
                  </div>
                ) : null}
              </SurfaceCardContent>
            </SurfaceCard>

            {canEdit ? (
              <div className="flex flex-wrap gap-3">
                <Button type="submit">Save draft</Button>
              </div>
            ) : null}
          </form>

          {agreementPreview?.status === "ready" && agreementPreview.mergeValues ? (
            <SurfaceCard>
              <PanelHeader title="Agreement preview" />
              <SurfaceCardContent>
                <dl className="grid gap-2 text-sm">
                  {Object.entries(agreementPreview.mergeValues)
                    .sort(([a], [b]) => a.localeCompare(b))
                    .map(([key, value]) => (
                      <div
                        key={key}
                        className="grid gap-1 border-b border-border/60 py-2 sm:grid-cols-[14rem_minmax(0,1fr)]"
                      >
                        <dt className="text-muted-foreground font-medium">{key}</dt>
                        <dd>{value || "—"}</dd>
                      </div>
                    ))}
                </dl>
              </SurfaceCardContent>
            </SurfaceCard>
          ) : null}
          {agreementPreview?.status === "error" ? (
            <p className="text-destructive text-sm" role="alert">
              {agreementPreview.message}
            </p>
          ) : null}
        </div>

        <aside className="grid gap-4 self-start">
          <SurfaceCard>
            <PanelHeader title="Lifecycle" />
            <SurfaceCardContent className="grid gap-2">
              {allowedActions.includes("submit_for_review") ? (
                <Button
                  type="button"
                  onClick={() => postLifecycle("submit_for_review")}
                >
                  Submit for review
                </Button>
              ) : null}
              {allowedActions.includes("reopen") ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => postLifecycle("reopen")}
                >
                  Reopen draft
                </Button>
              ) : null}
              {allowedActions.includes("issue") ? (
                <Button type="button" onClick={() => setConfirmAction("issue")}>
                  Issue / send
                </Button>
              ) : null}
              {allowedActions.includes("activate") ? (
                <Button type="button" onClick={() => setConfirmAction("activate")}>
                  Activate
                </Button>
              ) : null}
              {allowedActions.includes("retry_generation") ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => postLifecycle("retry_generation")}
                >
                  Retry PDF generation
                </Button>
              ) : null}
              {allowedActions.includes("supersede") ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setConfirmAction("supersede")}
                >
                  Supersede
                </Button>
              ) : null}
              {allowedActions.includes("terminate") ? (
                <Button
                  type="button"
                  variant="destructive"
                  onClick={() => setConfirmAction("terminate")}
                >
                  Terminate
                </Button>
              ) : null}
              {generatedPdfUrl ? (
                <Button type="button" variant="outline" asChild>
                  <a href={generatedPdfUrl}>Download review PDF</a>
                </Button>
              ) : null}
              {contract.status === "sent" && !generatedPdfUrl ? (
                <p className="text-sm text-muted-foreground">
                  Review PDF generation is in progress.
                </p>
              ) : null}
              {contract.status === "generation_error" ? (
                <p className="text-sm text-destructive" role="alert">
                  PDF generation failed. Retry after checking the template and
                  snapshots.
                </p>
              ) : null}
              {capabilities.canManage ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() =>
                    router.get(routes.agent_contract_preview(contract.publicId))
                  }
                >
                  Preview agreement
                </Button>
              ) : null}
            </SurfaceCardContent>
          </SurfaceCard>

          {commercialPreview ? (
            <CommissionCalculator
              contractPublicId={contract.publicId}
              initial={commercialPreview}
            />
          ) : null}
        </aside>

        {confirmCopy && confirmAction ? (
          <AccessChangeDialog
            open
            onOpenChange={(open) => {
              if (!open) setConfirmAction(null);
            }}
            title={confirmCopy.title}
            description={confirmCopy.description}
            changes={[
              {
                label: "Status",
                from: contract.statusLabel,
                to: confirmCopy.toLabel,
                impact: confirmCopy.impact,
              },
              {
                label: "Recipient",
                from: recipient.name,
                to: recipient.email,
                impact: `Effective ${contract.effectiveOn}.`,
              },
            ]}
            confirmLabel={confirmCopy.confirmLabel}
            onConfirm={() => {
              const action = confirmAction;
              setConfirmAction(null);
              postLifecycle(action, true);
            }}
          />
        ) : null}
      </div>
    </PermissionRequired>
  );
}

AgentContractWorkspace.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Agent contract",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Agent Contracts", href: routes.admin_agent_contracts() },
          { label: "Workspace" },
        ],
      },
      variant: "standard",
    },
  ] as const;
