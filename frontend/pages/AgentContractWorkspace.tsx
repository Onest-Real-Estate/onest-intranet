import { Head, Link, router, usePage } from "@inertiajs/react";
import { Download, FilePlus2, FileText, Replace } from "lucide-react";
import { useMemo, useState } from "react";
import { AccessChangeDialog } from "@/components/administration/AccessChangeDialog";
import { CommissionCalculator } from "@/components/administration/CommissionCalculator";
import { ContractLifecyclePanel } from "@/components/administration/ContractLifecyclePanel";
import {
  CONFIRM_LIFECYCLE,
  type ConfirmLifecycleAction,
  type ContractStamps,
  type LifecycleActionCode,
  needsConfirmation,
} from "@/components/administration/contract-lifecycle";
import { MergeValuePreview } from "@/components/administration/MergeValuePreview";
import { ContractPayeeSearch } from "@/components/ContractPayeeSearch";
import {
  Callout,
  NativeSelect,
  PageHeader,
  PanelHeader,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
  toStatusTone,
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

const ACCESS = {
  any: ["web.view_agent_contracts", "contract.manage_agent_contracts"],
};

/** Matches ``CommissionBasis.FIXED_ONLY`` — percent is invalid for this basis. */
const FIXED_ONLY_BASIS = "fixed_only";

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
    generatedPdfPreviewUrl = null,
    familyHistory = [],
    termComparison = null,
    companySignatoryOptions = [],
    csrfToken,
  } = usePage<AgentContractWorkspacePageProps>().props;
  const commission = contract.commission as Record<string, unknown> | undefined;
  const [confirmAction, setConfirmAction] = useState<ConfirmLifecycleAction | null>(
    null,
  );
  const [companySignatoryId, setCompanySignatoryId] = useState(() =>
    String(
      (contract as { companySignatoryId?: number | null }).companySignatoryId ?? "",
    ),
  );
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const canEdit = capabilities.canManage && contract.status === "draft";
  useValidationToasts(errors);
  const confirmCopy = confirmAction ? CONFIRM_LIFECYCLE[confirmAction] : null;
  const versionLabel = `v${contract.versionNumber ?? "—"} · ${
    contract.changeKindLabel ?? "Agreement"
  }`;
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
        ...(action === "issue" && companySignatoryId
          ? { company_signatory_id: companySignatoryId }
          : {}),
      }),
      { preserveScroll: true },
    );
  }

  /**
   * One entry point for every lifecycle button. The registry decides whether a
   * move needs the confirm dialog, so a new action can never reach the server
   * unconfirmed just because someone forgot to wire its `setConfirmAction`.
   */
  function runLifecycle(action: LifecycleActionCode) {
    if (needsConfirmation(action)) {
      setConfirmAction(action);
      return;
    }
    postLifecycle(action);
  }

  return (
    <PermissionRequired permission={ACCESS}>
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <Head title={`Contract · ${recipient.name}`} />
        <div className="grid gap-6">
          <PageHeader
            title={recipient.name}
            description={`${recipient.email} · ${officeName} · ${versionLabel}`}
            meta={
              <StatusBadge
                status={{
                  label: contract.statusLabel,
                  tone: toStatusTone(contract.statusTone),
                }}
              />
            }
          />

          {!canEdit ? (
            <Callout tone="neutral" title="This version is read-only">
              Issued and historical versions are immutable. Create an amendment or
              replacement draft to change terms.
            </Callout>
          ) : null}
          {contract.status === "awaiting_company_signature" ? (
            <Callout tone="warning" title="Awaiting company signature">
              {typeof contract.companySignatoryName === "string" &&
              contract.companySignatoryName
                ? contract.companySignatoryName
                : "The named officer"}{" "}
              must sign for the company before this agreement is released to the agent.
              {typeof contract.companySignUrl === "string" &&
              contract.companySignUrl ? (
                <>
                  {" "}
                  <Link
                    href={contract.companySignUrl}
                    className="text-primary underline"
                  >
                    Open company signing
                  </Link>
                </>
              ) : null}
            </Callout>
          ) : null}
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

            {(contract.changeKind === "amendment" ||
              contract.changeKind === "addendum" ||
              contract.changeKind === "replacement" ||
              canEdit) && (
              <SurfaceCard>
                <PanelHeader
                  title="Change summary"
                  description="Legal narrative for amendments and addenda. Shown on the agreement package."
                />
                <SurfaceCardContent>
                  <Label htmlFor="change_summary">Summary of changes</Label>
                  <Textarea
                    id="change_summary"
                    name="change_summary"
                    rows={4}
                    defaultValue={contract.changeSummary ?? ""}
                    disabled={!canEdit}
                    className="mt-2"
                  />
                </SurfaceCardContent>
              </SurfaceCard>
            )}

            {termComparison ? (
              <SurfaceCard>
                <PanelHeader
                  title="Before / after terms"
                  description={`Compared to base version ${termComparison.baseVersionNumber} (${termComparison.baseStatusLabel}). Review before issuing.`}
                />
                <SurfaceCardContent className="grid gap-4">
                  <p className="text-muted-foreground text-sm" role="note">
                    {termComparison.effectiveDateNote}
                  </p>
                  {termComparison.changeSummary ? (
                    <p className="text-sm whitespace-pre-line">
                      {termComparison.changeSummary}
                    </p>
                  ) : null}
                  {termComparison.rows.length === 0 ? (
                    <p className="text-muted-foreground text-sm">
                      No commercial term differences from the base yet.
                    </p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <caption className="sr-only">
                          Term changes between base version{" "}
                          {termComparison.baseVersionNumber} and this draft
                        </caption>
                        <thead>
                          <tr className="border-b border-border text-left">
                            <th scope="col" className="py-2 pr-3 font-medium">
                              Term
                            </th>
                            <th scope="col" className="py-2 pr-3 font-medium">
                              Before
                            </th>
                            <th scope="col" className="py-2 font-medium">
                              After
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {termComparison.rows.map((row) => (
                            <tr key={row.key} className="border-b border-border/60">
                              <th
                                scope="row"
                                className="py-2 pr-3 text-left font-normal text-muted-foreground"
                              >
                                {row.label}
                              </th>
                              <td className="py-2 pr-3">{row.before}</td>
                              <td className="py-2 font-medium">{row.after}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </SurfaceCardContent>
              </SurfaceCard>
            ) : null}
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

          {agreementPreview?.status === "ready" ? (
            <SurfaceCard>
              <PanelHeader
                title="Agreement preview"
                description={
                  generatedPdfPreviewUrl
                    ? "The issued review PDF with Prefill values applied. Signature fields stay blank until the ceremony."
                    : "Merge values for the agreement. The review PDF appears here once generation finishes."
                }
                divided
              />
              <SurfaceCardContent className="grid gap-4">
                {generatedPdfPreviewUrl ? (
                  <section
                    className="border-border bg-muted/30 relative min-h-[28rem] overflow-hidden rounded-lg border"
                    aria-label="Agreement PDF preview"
                  >
                    <object
                      data={`${generatedPdfPreviewUrl}#view=FitH`}
                      type="application/pdf"
                      className="h-[min(70vh,40rem)] w-full"
                      aria-label="Agreement PDF"
                    >
                      <div className="grid gap-3 p-6">
                        <p className="text-muted-foreground text-sm">
                          Embedded preview is not supported in this browser. Download
                          the PDF instead.
                        </p>
                        {generatedPdfUrl ? (
                          <Button type="button" variant="outline" size="sm" asChild>
                            <a href={generatedPdfUrl} download>
                              <Download className="size-4" aria-hidden />
                              Download review PDF
                            </a>
                          </Button>
                        ) : null}
                      </div>
                    </object>
                  </section>
                ) : contract.status === "awaiting_company_signature" ||
                  contract.status === "sent" ? (
                  <Callout tone="info" title="Review PDF is generating">
                    Generation runs in the background after issue. Refresh in a moment,
                    or open company signing once the PDF is ready.
                  </Callout>
                ) : null}
                {agreementPreview.mergeValues ? (
                  <MergeValuePreview values={agreementPreview.mergeValues} />
                ) : null}
              </SurfaceCardContent>
            </SurfaceCard>
          ) : null}
          {agreementPreview?.status === "error" ? (
            <Callout tone="destructive" title="Preview could not be built">
              <span role="alert">{agreementPreview.message}</span>
            </Callout>
          ) : null}
        </div>

        <aside className="grid gap-4 self-start">
          <ContractLifecyclePanel
            status={contract.status}
            statusLabel={contract.statusLabel}
            stamps={contract as ContractStamps}
            allowedActions={allowedActions}
            onRun={runLifecycle}
            footer={
              contract.status === "generation_error" ? (
                <Callout tone="destructive" title="PDF generation failed">
                  Check the template version and the party and office snapshots, then
                  retry.
                </Callout>
              ) : (contract.status === "sent" ||
                  contract.status === "awaiting_company_signature") &&
                !generatedPdfUrl ? (
                <Callout tone="info" title="Review PDF is generating">
                  The download appears here once the agreement PDF is stored.
                </Callout>
              ) : null
            }
          />

          {generatedPdfUrl || capabilities.canManage ? (
            <SurfaceCard>
              <PanelHeader
                title="Documents"
                description="The issued agreement and a merge-field preview of it."
              />
              <SurfaceCardContent className="grid gap-2">
                {generatedPdfUrl ? (
                  <Button
                    type="button"
                    variant="outline"
                    className="w-full justify-start"
                    asChild
                  >
                    <a href={generatedPdfUrl} download>
                      <Download className="size-4" aria-hidden />
                      Download review PDF
                    </a>
                  </Button>
                ) : null}
                {generatedPdfPreviewUrl ? (
                  <Button
                    type="button"
                    variant="outline"
                    className="w-full justify-start"
                    asChild
                  >
                    <a
                      href={generatedPdfPreviewUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <FileText className="size-4" aria-hidden />
                      Open review PDF
                    </a>
                  </Button>
                ) : null}
                {capabilities.canManage ? (
                  <Button
                    type="button"
                    variant="outline"
                    className="w-full justify-start"
                    onClick={() =>
                      router.get(routes.agent_contract_preview(contract.publicId))
                    }
                  >
                    <FileText className="size-4" aria-hidden />
                    Preview agreement
                  </Button>
                ) : null}
              </SurfaceCardContent>
            </SurfaceCard>
          ) : null}

          {capabilities.canCreateAmendment || capabilities.canCreateReplacement ? (
            <SurfaceCard>
              <PanelHeader
                title="New version"
                description="Issued versions are immutable. Both moves open a fresh draft and leave this one untouched."
              />
              <SurfaceCardContent className="grid gap-3">
                {capabilities.canCreateAmendment ? (
                  <div className="grid gap-1">
                    <Button
                      type="button"
                      variant="outline"
                      className="w-full justify-start"
                      onClick={() =>
                        router.post(
                          routes.agent_contract_create_amendment(contract.publicId),
                          toFormData({ change_kind: "amendment" }),
                        )
                      }
                    >
                      <FilePlus2 className="size-4" aria-hidden />
                      Create amendment
                    </Button>
                    <p className="text-muted-foreground px-1 text-xs leading-4">
                      Changes specific terms and keeps this agreement in force.
                    </p>
                  </div>
                ) : null}
                {capabilities.canCreateReplacement ? (
                  <div className="grid gap-1">
                    <Button
                      type="button"
                      variant="outline"
                      className="w-full justify-start"
                      onClick={() =>
                        router.post(
                          routes.agent_contract_create_replacement(contract.publicId),
                          toFormData({}),
                        )
                      }
                    >
                      <Replace className="size-4" aria-hidden />
                      Create replacement
                    </Button>
                    <p className="text-muted-foreground px-1 text-xs leading-4">
                      Supersedes this agreement with a new one from the start.
                    </p>
                  </div>
                ) : null}
              </SurfaceCardContent>
            </SurfaceCard>
          ) : null}

          {commercialPreview ? (
            <CommissionCalculator
              contractPublicId={contract.publicId}
              initial={commercialPreview}
            />
          ) : null}

          {familyHistory.length > 0 ? (
            <SurfaceCard>
              <PanelHeader
                title="Family history"
                description="Base, amendments, replacements, and supersession in this family."
              />
              <SurfaceCardContent>
                <ul className="grid gap-2">
                  {familyHistory.map((row) => (
                    <li key={row.publicId}>
                      <Link
                        href={row.href}
                        className={`border-border flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3 text-sm ${
                          row.isFocus ? "bg-muted/40" : "hover:bg-muted/30"
                        }`}
                        aria-current={row.isFocus ? "page" : undefined}
                        preserveScroll
                      >
                        <div className="grid min-w-0 gap-0.5">
                          <span className="font-medium">
                            Version {row.versionNumber} · {row.changeKindLabel}
                          </span>
                          <span className="text-muted-foreground text-xs">
                            {row.governing === "current"
                              ? "Currently governing"
                              : row.governing === "historical"
                                ? "Historical"
                                : "In flight"}
                            {row.amendsPublicId ? " · Amends prior version" : ""}
                            {row.supersedesPublicId
                              ? " · Supersedes prior version"
                              : ""}
                          </span>
                        </div>
                        <StatusBadge
                          status={{
                            label: row.statusLabel,
                            tone: toStatusTone(row.statusTone),
                          }}
                        />
                      </Link>
                    </li>
                  ))}
                </ul>
              </SurfaceCardContent>
            </SurfaceCard>
          ) : null}
        </aside>

        {confirmCopy && confirmAction ? (
          <AccessChangeDialog
            open
            onOpenChange={(open) => {
              if (!open) setConfirmAction(null);
            }}
            title={confirmCopy.title}
            description={
              confirmAction === "issue" && termComparison
                ? `${confirmCopy.description} ${termComparison.rows.length} term difference(s) vs base v${termComparison.baseVersionNumber}. ${termComparison.effectiveDateNote}`
                : confirmCopy.description
            }
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
              if (confirmAction === "issue" && !companySignatoryId) {
                return;
              }
              const action = confirmAction;
              setConfirmAction(null);
              postLifecycle(action, true);
            }}
          >
            {confirmAction === "issue" ? (
              <div className="grid gap-2">
                <Label htmlFor="company-signatory">Company signatory</Label>
                <Select
                  value={companySignatoryId || undefined}
                  onValueChange={setCompanySignatoryId}
                >
                  <SelectTrigger id="company-signatory">
                    <SelectValue placeholder="Choose the officer who signs first" />
                  </SelectTrigger>
                  <SelectContent>
                    {companySignatoryOptions.map((option) => (
                      <SelectItem key={option.id} value={String(option.id)}>
                        {option.name} · {option.email}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {!companySignatoryId ? (
                  <p className="text-destructive text-xs">
                    Choose a company signatory before issuing.
                  </p>
                ) : null}
              </div>
            ) : null}
          </AccessChangeDialog>
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
