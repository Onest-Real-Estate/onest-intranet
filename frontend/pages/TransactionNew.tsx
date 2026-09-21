import { Head, router, usePage } from "@inertiajs/react";
import { useId, useState } from "react";
import { AccessChangeDialog } from "@/components/administration/AccessChangeDialog";
import {
  PersonCombobox,
  type PersonOption,
} from "@/components/administration/PersonCombobox";
import {
  DateField,
  FormActionBar,
  FormDescription,
  FormErrorSummary,
  FormField,
  FormFieldError,
  FormLabel,
  fieldA11yProps,
  PageHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { routes } from "@/lib/routes";
import { hasValidationErrors } from "@/lib/validation";
import type { TransactionNewPageProps } from "@/types";

const ACCESS = {
  any: ["web.manage_transactions", "web.create_own_transactions"],
};

function fieldRequired(required: string[], name: string): boolean {
  return required.includes(name);
}

function fieldLocked(locked: string[], name: string): boolean {
  return locked.includes(name);
}

export default function TransactionNew() {
  const { schema, draft, errors, duplicates, offices, capabilities, selfPerson } =
    usePage<TransactionNewPageProps>().props;

  const [submissionKey] = useState(() => draft.submissionKey || crypto.randomUUID());
  const [transactionType, setTransactionType] = useState(draft.transactionType || "");
  const [representationType, setRepresentationType] = useState(
    draft.representationType || "",
  );
  const [officeKey, setOfficeKey] = useState(
    draft.officeKey || (capabilities.lockOffice ? selfPerson.officeKey || "" : ""),
  );
  const [primaryAgent, setPrimaryAgent] = useState<PersonOption | null>(() =>
    capabilities.lockPrimaryAgent
      ? selfPerson
      : draft.primaryAgentId
        ? {
            id: Number(draft.primaryAgentId),
            name: draft.primaryAgentName || "Selected agent",
            email: draft.primaryAgentEmail || "",
            officeId: null,
            officeName: "",
            licenseState: "",
            agentIdentifier: "",
          }
        : null,
  );
  const [coAgent, setCoAgent] = useState<PersonOption | null>(null);
  const [coordinator, setCoordinator] = useState<PersonOption | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(duplicates.length > 0);
  const [submitting, setSubmitting] = useState(false);
  const formId = useId();

  const required = schema.requiredFields;
  const locked = schema.lockedFields;
  const peopleEndpoint = (role: "agent" | "coordinator") =>
    `${routes.transaction_people_search()}?role=${role}`;

  function post(action: "draft" | "prepare", confirmedDuplicate = false) {
    if (submitting) return;
    setSubmitting(true);
    const form = document.getElementById(formId) as HTMLFormElement | null;
    if (!form) {
      setSubmitting(false);
      return;
    }
    const data = new FormData(form);
    data.set("submissionKey", submissionKey);
    if (confirmedDuplicate) data.set("confirmedDuplicate", "1");
    const url =
      action === "draft"
        ? routes.transaction_draft_save()
        : routes.transaction_prepare();
    router.post(url, data, {
      preserveScroll: true,
      onFinish: () => setSubmitting(false),
      onSuccess: () => setConfirmOpen(false),
    });
  }

  return (
    <PermissionRequired permission={ACCESS}>
      <Head title="New transaction" />
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 py-6">
        <PageHeader
          title="New transaction"
          description="Capture the deal basics, save a draft when needed, then prepare when the required fields are ready."
        />

        {hasValidationErrors(errors) ? <FormErrorSummary errors={errors} /> : null}

        {duplicates.length > 0 ? (
          <SurfaceCard>
            <SurfaceCardContent className="space-y-2 py-4">
              <p className="text-sm font-medium">Possible duplicates in your scope</p>
              <ul className="text-muted-foreground list-inside list-disc text-sm">
                {duplicates.map((row) => (
                  <li key={row.publicId}>{row.reference}</li>
                ))}
              </ul>
            </SurfaceCardContent>
          </SurfaceCard>
        ) : null}

        <form
          id={formId}
          className="flex flex-col gap-6"
          onSubmit={(event) => {
            event.preventDefault();
            if (duplicates.length > 0) {
              setConfirmOpen(true);
              return;
            }
            post("prepare");
          }}
        >
          <input type="hidden" name="submissionKey" value={submissionKey} />
          {draft.publicId ? (
            <input type="hidden" name="publicId" value={draft.publicId} />
          ) : null}

          <SurfaceCard>
            <SurfaceCardContent className="grid gap-4 py-5 sm:grid-cols-2">
              <FormField>
                <FormLabel htmlFor="transactionType" required>
                  Transaction type
                </FormLabel>
                <Select
                  value={transactionType}
                  onValueChange={(value) => {
                    setTransactionType(value);
                    setRepresentationType("");
                  }}
                  disabled={submitting}
                >
                  <SelectTrigger
                    id="transactionType"
                    {...fieldA11yProps("transactionType", errors)}
                  >
                    <SelectValue placeholder="Select type" />
                  </SelectTrigger>
                  <SelectContent>
                    {schema.transactionTypes.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <input type="hidden" name="transactionType" value={transactionType} />
                <FormFieldError messages={errors.fields?.transactionType} />
              </FormField>

              <FormField>
                <FormLabel htmlFor="representationType" required>
                  Representation
                </FormLabel>
                <Select
                  value={representationType}
                  onValueChange={setRepresentationType}
                  disabled={submitting || !transactionType}
                >
                  <SelectTrigger
                    id="representationType"
                    {...fieldA11yProps("representationType", errors)}
                  >
                    <SelectValue placeholder="Select representation" />
                  </SelectTrigger>
                  <SelectContent>
                    {schema.representationTypes.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <input
                  type="hidden"
                  name="representationType"
                  value={representationType}
                />
                <FormFieldError messages={errors.fields?.representationType} />
              </FormField>
            </SurfaceCardContent>
          </SurfaceCard>

          <SurfaceCard>
            <SurfaceCardContent className="grid gap-4 py-5 sm:grid-cols-2">
              <FormField className="sm:col-span-2">
                <FormLabel
                  htmlFor="propertyLine1"
                  required={fieldRequired(required, "propertyLine1")}
                >
                  Property street
                </FormLabel>
                <Input
                  id="propertyLine1"
                  name="propertyLine1"
                  defaultValue={draft.propertyLine1 || ""}
                  disabled={submitting}
                  {...fieldA11yProps("propertyLine1", errors)}
                />
                <FormFieldError messages={errors.fields?.propertyLine1} />
              </FormField>
              <FormField className="sm:col-span-2">
                <FormLabel htmlFor="propertyLine2">Unit / line 2</FormLabel>
                <Input
                  id="propertyLine2"
                  name="propertyLine2"
                  defaultValue={draft.propertyLine2 || ""}
                  disabled={submitting}
                />
              </FormField>
              <FormField>
                <FormLabel htmlFor="propertyCity">City</FormLabel>
                <Input
                  id="propertyCity"
                  name="propertyCity"
                  defaultValue={draft.propertyCity || ""}
                  disabled={submitting}
                />
              </FormField>
              <FormField>
                <FormLabel htmlFor="propertyState">State</FormLabel>
                <Input
                  id="propertyState"
                  name="propertyState"
                  defaultValue={draft.propertyState || ""}
                  disabled={submitting}
                />
              </FormField>
              <FormField>
                <FormLabel htmlFor="propertyPostalCode">Postal code</FormLabel>
                <Input
                  id="propertyPostalCode"
                  name="propertyPostalCode"
                  defaultValue={draft.propertyPostalCode || ""}
                  disabled={submitting}
                />
              </FormField>
              <FormField>
                <FormLabel htmlFor="mlsNumber">MLS number</FormLabel>
                <Input
                  id="mlsNumber"
                  name="mlsNumber"
                  defaultValue={draft.mlsNumber || ""}
                  disabled={submitting}
                />
                <FormFieldError messages={errors.fields?.mlsNumber} />
              </FormField>
            </SurfaceCardContent>
          </SurfaceCard>

          <SurfaceCard>
            <SurfaceCardContent className="grid gap-4 py-5 sm:grid-cols-2">
              <FormField className="sm:col-span-2">
                <FormLabel
                  htmlFor="clientName"
                  required={fieldRequired(required, "clientName")}
                >
                  Primary client name
                </FormLabel>
                <Input
                  id="clientName"
                  name="clientName"
                  defaultValue={draft.clientName || ""}
                  disabled={submitting}
                  {...fieldA11yProps("clientName", errors)}
                />
                <FormFieldError messages={errors.fields?.clientName} />
              </FormField>
              <FormField>
                <FormLabel htmlFor="clientEmail">Client email</FormLabel>
                <Input
                  id="clientEmail"
                  name="clientEmail"
                  type="email"
                  defaultValue={draft.clientEmail || ""}
                  disabled={submitting}
                />
              </FormField>
              <FormField>
                <FormLabel htmlFor="clientPhone">Client phone</FormLabel>
                <Input
                  id="clientPhone"
                  name="clientPhone"
                  defaultValue={draft.clientPhone || ""}
                  disabled={submitting}
                />
              </FormField>
              <FormField>
                <FormLabel htmlFor="clientRole">Client role</FormLabel>
                <Input
                  id="clientRole"
                  name="clientRole"
                  defaultValue={draft.clientRole || ""}
                  disabled={submitting}
                  placeholder="buyer, seller, tenant…"
                />
              </FormField>
            </SurfaceCardContent>
          </SurfaceCard>

          <SurfaceCard>
            <SurfaceCardContent className="grid gap-4 py-5">
              <FormField>
                <FormLabel htmlFor="officeKey" required>
                  Owning office
                </FormLabel>
                <Select
                  value={officeKey}
                  onValueChange={setOfficeKey}
                  disabled={
                    submitting ||
                    fieldLocked(locked, "officeKey") ||
                    offices.length === 0
                  }
                >
                  <SelectTrigger
                    id="officeKey"
                    {...fieldA11yProps("officeKey", errors)}
                  >
                    <SelectValue placeholder="Select office" />
                  </SelectTrigger>
                  <SelectContent>
                    {offices.map((office) => (
                      <SelectItem key={office.stableKey} value={office.stableKey}>
                        {office.name}
                        {office.state ? ` (${office.state})` : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <input type="hidden" name="officeKey" value={officeKey} />
                <FormFieldError messages={errors.fields?.officeKey} />
              </FormField>

              <PersonCombobox
                id="primaryAgent"
                name="primaryAgentId"
                label="Primary agent"
                endpoint={peopleEndpoint("agent")}
                value={primaryAgent}
                onChange={setPrimaryAgent}
                disabled={submitting || fieldLocked(locked, "primaryAgentId")}
                required={fieldRequired(required, "primaryAgentId")}
                invalid={Boolean(errors.fields?.primaryAgentId?.length)}
              />
              <FormFieldError messages={errors.fields?.primaryAgentId} />

              {!capabilities.lockPrimaryAgent ? (
                <PersonCombobox
                  id="coAgent"
                  name="coAgentId"
                  label="Co-agent"
                  endpoint={peopleEndpoint("agent")}
                  value={coAgent}
                  onChange={setCoAgent}
                  disabled={submitting}
                />
              ) : null}

              <PersonCombobox
                id="coordinator"
                name="coordinatorId"
                label="Coordinator"
                endpoint={peopleEndpoint("coordinator")}
                value={coordinator}
                onChange={setCoordinator}
                disabled={submitting}
              />
              <FormFieldError messages={errors.fields?.coordinatorId} />
            </SurfaceCardContent>
          </SurfaceCard>

          <SurfaceCard>
            <SurfaceCardContent className="grid gap-4 py-5 sm:grid-cols-2">
              <FormField>
                <FormLabel htmlFor="listPrice">List price</FormLabel>
                <Input
                  id="listPrice"
                  name="listPrice"
                  inputMode="decimal"
                  defaultValue={draft.listPrice || ""}
                  disabled={submitting}
                />
                <FormFieldError messages={errors.fields?.listPrice} />
              </FormField>
              <FormField>
                <FormLabel htmlFor="contractPrice">Contract price</FormLabel>
                <Input
                  id="contractPrice"
                  name="contractPrice"
                  inputMode="decimal"
                  defaultValue={draft.contractPrice || ""}
                  disabled={submitting}
                />
                <FormFieldError messages={errors.fields?.contractPrice} />
              </FormField>
              <DateField
                name="acceptanceDate"
                label="Acceptance date"
                defaultValue={draft.acceptanceDate || ""}
                disabled={submitting}
                validation={errors}
              />
              <DateField
                name="closingDate"
                label="Closing date"
                defaultValue={draft.closingDate || ""}
                disabled={submitting}
                validation={errors}
              />
            </SurfaceCardContent>
          </SurfaceCard>

          <SurfaceCard>
            <SurfaceCardContent className="grid gap-4 py-5 sm:grid-cols-2">
              <FormField>
                <FormLabel htmlFor="lenderRef">Lender</FormLabel>
                <Input
                  id="lenderRef"
                  name="lenderRef"
                  defaultValue={draft.lenderRef || ""}
                  disabled={submitting}
                />
              </FormField>
              <FormField>
                <FormLabel htmlFor="titleRef">Title company</FormLabel>
                <Input
                  id="titleRef"
                  name="titleRef"
                  defaultValue={draft.titleRef || ""}
                  disabled={submitting}
                />
              </FormField>
              <FormField className="sm:col-span-2">
                <FormLabel htmlFor="referralRef">Referral source</FormLabel>
                <Input
                  id="referralRef"
                  name="referralRef"
                  defaultValue={draft.referralRef || ""}
                  disabled={submitting}
                />
                <FormDescription>
                  Free-text reference until CRM vendors ship.
                </FormDescription>
              </FormField>
            </SurfaceCardContent>
          </SurfaceCard>

          <FormActionBar status="Saves a draft or prepares the deal when required fields are ready.">
            <Button
              type="button"
              variant="outline"
              disabled={submitting}
              onClick={() => post("draft")}
            >
              Save draft
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Working…" : "Create / prepare"}
            </Button>
          </FormActionBar>
        </form>
      </div>

      <AccessChangeDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Confirm possible duplicate"
        description="Similar transactions already exist in your scope. Confirm only if this is a distinct deal."
        changes={duplicates.map((row) => ({
          label: row.reference,
          from: "Existing deal",
          to: "New deal",
          impact: "Creating anyway will leave both files open.",
        }))}
        confirmLabel="Create anyway"
        submitting={submitting}
        onConfirm={() => post("prepare", true)}
      />
    </PermissionRequired>
  );
}

TransactionNew.layout = (page: React.ReactNode) => <HubLayout>{page}</HubLayout>;
