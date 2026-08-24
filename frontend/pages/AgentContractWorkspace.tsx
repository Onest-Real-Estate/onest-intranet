import { Head, router, usePage } from "@inertiajs/react";
import { useMemo, useState } from "react";
import { AccessChangeDialog } from "@/components/administration/AccessChangeDialog";
import {
  FormErrorSummary,
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
import { Textarea } from "@/components/ui/textarea";
import { routes } from "@/lib/routes";
import type { AgentContractWorkspacePageProps } from "@/types";
import type { StatusTone } from "@/types/design-system";

const ACCESS = {
  any: ["web.view_agent_contracts", "contract.manage_agent_contracts"],
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

export default function AgentContractWorkspace() {
  const {
    contract,
    expectedVersion,
    capabilities,
    allowedActions,
    recipient,
    office,
    templateOptions,
    commercialPreview,
    errors,
    agreementPreview,
    csrfToken,
  } = usePage<AgentContractWorkspacePageProps>().props;
  const commission = contract.commission as Record<string, unknown> | undefined;
  const [issueOpen, setIssueOpen] = useState(false);
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const canEdit = capabilities.canManage && contract.status === "draft";

  const officeName = useMemo(
    () => String((office as { name?: string }).name ?? ""),
    [office],
  );

  function postLifecycle(action: string, confirmed = false) {
    router.post(
      routes.agent_contract_lifecycle(contract.publicId),
      {
        action,
        expected_version: expectedVersion,
        confirmed: confirmed ? "1" : "",
        idempotency_key: idempotencyKey,
      },
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
          <FormErrorSummary errors={errors} />

          <form
            method="post"
            action={routes.agent_contract_update(contract.publicId)}
            className="grid gap-6"
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
                  <select
                    id="template_version_id"
                    name="template_version_id"
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
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
                  </select>
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
                    description="Separate from referral. Basis and payee required when amounts are set."
                  />
                  <SurfaceCardContent className="grid gap-4 md:grid-cols-2">
                    <div className="grid gap-2">
                      <Label htmlFor="mentor_percent">Mentor percent (%)</Label>
                      <Input
                        id="mentor_percent"
                        name="mentor_percent"
                        defaultValue={nested(commission, "mentor", "percent")}
                        disabled={!canEdit}
                      />
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="mentor_fixed_amount">Mentor fixed (USD)</Label>
                      <Input
                        id="mentor_fixed_amount"
                        name="mentor_fixed_amount"
                        defaultValue={nested(commission, "mentor", "fixedAmount")}
                        disabled={!canEdit}
                      />
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="mentor_basis">Mentor basis</Label>
                      <Input
                        id="mentor_basis"
                        name="mentor_basis"
                        defaultValue={nested(commission, "mentor", "basis")}
                        disabled={!canEdit}
                        placeholder="agent_side_before_fees"
                      />
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="mentor_payee_id">Mentor payee id</Label>
                      <Input
                        id="mentor_payee_id"
                        name="mentor_payee_id"
                        defaultValue={nested(commission, "mentor", "payeeId")}
                        disabled={!canEdit}
                      />
                    </div>
                  </SurfaceCardContent>
                </SurfaceCard>

                <SurfaceCard>
                  <PanelHeader
                    title="Referral terms"
                    description="Calculated in parallel with mentor — neither reduces the other's base."
                  />
                  <SurfaceCardContent className="grid gap-4 md:grid-cols-2">
                    <div className="grid gap-2">
                      <Label htmlFor="referral_percent">Referral percent (%)</Label>
                      <Input
                        id="referral_percent"
                        name="referral_percent"
                        defaultValue={nested(commission, "referral", "percent")}
                        disabled={!canEdit}
                      />
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="referral_fixed_amount">
                        Referral fixed (USD)
                      </Label>
                      <Input
                        id="referral_fixed_amount"
                        name="referral_fixed_amount"
                        defaultValue={nested(commission, "referral", "fixedAmount")}
                        disabled={!canEdit}
                      />
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="referral_basis">Referral basis</Label>
                      <Input
                        id="referral_basis"
                        name="referral_basis"
                        defaultValue={nested(commission, "referral", "basis")}
                        disabled={!canEdit}
                      />
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="referral_payee_id">Referral payee id</Label>
                      <Input
                        id="referral_payee_id"
                        name="referral_payee_id"
                        defaultValue={nested(commission, "referral", "payeeId")}
                        disabled={!canEdit}
                      />
                    </div>
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
                <Button type="button" onClick={() => setIssueOpen(true)}>
                  Issue / send
                </Button>
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
            <SurfaceCard>
              <PanelHeader
                title="Financial breakdown"
                description="Sample GCI worksheet (server-calculated)."
              />
              <SurfaceCardContent className="grid gap-2 text-sm">
                <ul className="grid gap-1">
                  {commercialPreview.summaryLines.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
                {commercialPreview.breakdown ? (
                  <dl className="grid gap-1 border-t border-border pt-2">
                    <div className="flex justify-between gap-2">
                      <dt>Agent net</dt>
                      <dd>
                        {commercialPreview.breakdown.agentNet}{" "}
                        {commercialPreview.breakdown.currency}
                      </dd>
                    </div>
                    <div className="flex justify-between gap-2">
                      <dt>Office net</dt>
                      <dd>
                        {commercialPreview.breakdown.officeNet}{" "}
                        {commercialPreview.breakdown.currency}
                      </dd>
                    </div>
                    <div className="flex justify-between gap-2">
                      <dt>Rule</dt>
                      <dd>{commercialPreview.breakdown.ruleVersion}</dd>
                    </div>
                  </dl>
                ) : null}
              </SurfaceCardContent>
            </SurfaceCard>
          ) : null}
        </aside>

        <AccessChangeDialog
          open={issueOpen}
          onOpenChange={setIssueOpen}
          title="Issue this contract?"
          description="Freezes party, office, terms, template version, and calculation rule version, then queues PDF generation and marks the contract sent."
          changes={[
            {
              label: "Status",
              from: contract.statusLabel,
              to: "Sent to agent",
              impact: "Agent can review the issued agreement after PDF generation.",
            },
            {
              label: "Recipient",
              from: recipient.name,
              to: recipient.email,
              impact: `Effective ${contract.effectiveOn}.`,
            },
          ]}
          confirmLabel="Confirm issue"
          onConfirm={() => {
            setIssueOpen(false);
            postLifecycle("issue", true);
          }}
        />
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
