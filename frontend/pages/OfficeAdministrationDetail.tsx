import { Head, Link, router, usePage } from "@inertiajs/react";
import { Contact, ExternalLink } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  type AccessChange,
  AccessChangeDialog,
} from "@/components/administration/AccessChangeDialog";
import {
  EmptyState,
  FormActionBar,
  FormErrorSummary,
  FormField,
  FormLabel,
  PageHeader,
  PanelHeader,
  ReadOnlyValue,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { OfficeInfoPanel } from "@/components/office/OfficeInfoPanel";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { routes } from "@/lib/routes";
import { hasValidationErrors } from "@/lib/validation";
import type { OfficeAdministrationDetailPageProps } from "@/types";

const MANAGE = { all: ["web.manage_offices"] };

const ERROR_LABELS: Record<string, string> = {
  name: "Name",
  street_address: "Street address",
  city: "City",
  state: "State",
  zip_code: "ZIP code",
  main_phone: "Main phone",
  public_email: "Public email",
  internal_email: "Internal email",
  office_hours: "Office hours",
  parking_instructions: "Parking",
  access_instructions: "Access instructions",
  parent: "Parent",
  kind: "Kind",
  user: "Contact",
  assignment_type: "Contact type",
  ends_at: "End date",
};

function OfficeAdministrationDetailPage() {
  const { csrfToken, administration, validation, preview, scope } =
    usePage<OfficeAdministrationDetailPageProps>().props;
  const { office, contacts, capabilities, version, resourceLinks, agentPreview } =
    administration;
  const [submitting, setSubmitting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [structureImpact, setStructureImpact] = useState<AccessChange[]>(
    preview?.highImpact ?? [],
  );
  const [parentId, setParentId] = useState(
    office.parentId != null ? String(office.parentId) : "",
  );
  const [kind, setKind] = useState(office.kind);
  const [isActive, setIsActive] = useState(office.isActive);
  const [isAssignable, setIsAssignable] = useState(office.isAssignable);
  const [accessInternal, setAccessInternal] = useState(
    office.accessInstructionsInternal,
  );
  const [contactType, setContactType] = useState(
    administration.contactTypes[0]?.value ?? "manager",
  );
  const [contactUserId, setContactUserId] = useState(
    administration.contactCandidates[0]
      ? String(administration.contactCandidates[0].id)
      : "",
  );
  const [contactPrimary, setContactPrimary] = useState(false);
  const structureFormRef = useRef<HTMLFormElement>(null);
  const summaryRef = useRef<HTMLDivElement>(null);
  const hasErrors = hasValidationErrors(validation);

  useEffect(() => {
    if (hasErrors) summaryRef.current?.focus();
  }, [hasErrors]);

  useEffect(() => {
    if (preview?.highImpact?.length) {
      setStructureImpact(preview.highImpact);
      setConfirming(true);
    }
  }, [preview]);

  function submitStructure(confirmed: boolean) {
    const form = structureFormRef.current;
    if (!form) return;
    const data = new FormData(form);
    if (confirmed) data.set("confirmed", "1");
    setSubmitting(true);
    router.post(routes.admin_office_structure(office.id), data, {
      onFinish: () => setSubmitting(false),
    });
  }

  return (
    <div className="flex flex-col gap-10">
      <Head title={`${office.name} · Offices`} />
      <PageHeader
        title={office.name}
        description={office.pathLabel}
        meta={
          <span className="flex items-center gap-2">
            <StatusBadge
              status={{
                label: office.isActive ? "Active" : "Inactive",
                tone: office.isActive ? "success" : "neutral",
              }}
            />
            <span className="text-muted-foreground text-sm">{scope.label}</span>
          </span>
        }
      />

      <div ref={summaryRef} tabIndex={-1} className="outline-none">
        <FormErrorSummary errors={validation} labels={ERROR_LABELS} />
      </div>

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(18rem,22rem)]">
        <div className="grid content-start gap-6">
          <SurfaceCard>
            <PanelHeader
              divided
              title="Identity"
              description="Stable key never changes. Kind and parent require company authority."
            />
            <SurfaceCardContent className="grid gap-3 sm:grid-cols-2">
              <ReadOnlyValue label="Stable key">
                <span className="font-medium">{office.stableKey}</span>
              </ReadOnlyValue>
              <ReadOnlyValue label="Slug">
                <span className="font-medium">{office.slug}</span>
              </ReadOnlyValue>
              <ReadOnlyValue label="Kind">
                <span className="font-medium">{office.kindLabel}</span>
              </ReadOnlyValue>
              <ReadOnlyValue label="Parent">
                <span className="font-medium">{office.parentPathLabel ?? "—"}</span>
              </ReadOnlyValue>
            </SurfaceCardContent>
          </SurfaceCard>

          <form
            method="post"
            action={routes.admin_office_update(office.id)}
            className="grid gap-6"
            onSubmit={() => setSubmitting(true)}
          >
            <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
            <input type="hidden" name="expected_version" value={version} />

            <SurfaceCard>
              <PanelHeader
                divided
                title="Location and contact"
                description="Public branch details agents see on Office Info."
              />
              <SurfaceCardContent className="grid gap-4 sm:grid-cols-2">
                <FormField className="sm:col-span-2">
                  <FormLabel htmlFor="name">Name</FormLabel>
                  <Input id="name" name="name" defaultValue={office.name} required />
                </FormField>
                <FormField className="sm:col-span-2">
                  <FormLabel htmlFor="street_address">Street address</FormLabel>
                  <Input
                    id="street_address"
                    name="street_address"
                    defaultValue={office.streetAddress}
                  />
                </FormField>
                <FormField>
                  <FormLabel htmlFor="city">City</FormLabel>
                  <Input id="city" name="city" defaultValue={office.city} />
                </FormField>
                <FormField>
                  <FormLabel htmlFor="state">State</FormLabel>
                  <Input
                    id="state"
                    name="state"
                    defaultValue={office.state}
                    maxLength={2}
                  />
                </FormField>
                <FormField>
                  <FormLabel htmlFor="zip_code">ZIP code</FormLabel>
                  <Input id="zip_code" name="zip_code" defaultValue={office.zipCode} />
                </FormField>
                <FormField>
                  <FormLabel htmlFor="main_phone">Main phone</FormLabel>
                  <Input
                    id="main_phone"
                    name="main_phone"
                    defaultValue={office.mainPhone}
                  />
                </FormField>
                <FormField>
                  <FormLabel htmlFor="public_email">Public email</FormLabel>
                  <Input
                    id="public_email"
                    name="public_email"
                    type="email"
                    defaultValue={office.publicEmail}
                  />
                </FormField>
                <FormField>
                  <FormLabel htmlFor="internal_email">Internal email</FormLabel>
                  <Input
                    id="internal_email"
                    name="internal_email"
                    type="email"
                    defaultValue={office.internalEmail}
                  />
                </FormField>
                <FormField className="sm:col-span-2">
                  <FormLabel htmlFor="office_hours_text">Office hours</FormLabel>
                  <Textarea
                    id="office_hours_text"
                    name="office_hours_text"
                    rows={4}
                    defaultValue={office.officeHoursText}
                  />
                </FormField>
              </SurfaceCardContent>
            </SurfaceCard>

            <SurfaceCard>
              <PanelHeader
                divided
                title="Instructions"
                description="Internal access copy stays authenticated and field-protected."
              />
              <SurfaceCardContent className="grid gap-4">
                <FormField>
                  <FormLabel htmlFor="parking_instructions">Parking</FormLabel>
                  <Textarea
                    id="parking_instructions"
                    name="parking_instructions"
                    rows={3}
                    defaultValue={office.parkingInstructions}
                  />
                </FormField>
                <FormField>
                  <FormLabel htmlFor="access_instructions">
                    Access instructions
                  </FormLabel>
                  <Textarea
                    id="access_instructions"
                    name="access_instructions"
                    rows={3}
                    defaultValue={office.accessInstructions}
                  />
                </FormField>
                <div className="flex items-center gap-2 text-sm">
                  <Checkbox
                    id="access_instructions_internal"
                    checked={accessInternal}
                    onCheckedChange={(checked) => setAccessInternal(checked === true)}
                  />
                  <input
                    type="hidden"
                    name="access_instructions_internal"
                    value={accessInternal ? "on" : ""}
                  />
                  <label htmlFor="access_instructions_internal">
                    Treat access instructions as internal
                  </label>
                </div>
              </SurfaceCardContent>
            </SurfaceCard>

            <FormActionBar
              status={
                submitting ? "Saving…" : "Changes are recorded in the audit trail."
              }
            >
              <Button type="submit" disabled={submitting}>
                Save office info
              </Button>
            </FormActionBar>
          </form>

          <SurfaceCard>
            <PanelHeader
              divided
              title="Contact assignments"
              description="Branch manager, admin, broker, TC, and IT support with validity dates."
            />
            <SurfaceCardContent className="grid gap-6">
              {contacts.length === 0 ? (
                <EmptyState
                  icon={Contact}
                  compact
                  title="No contact assignments yet"
                  description="Assign a branch manager, admin, broker, TC, or IT contact to fill this list."
                />
              ) : (
                <ul className="grid gap-3">
                  {contacts.map((contact) => (
                    <li
                      key={contact.id}
                      className="border-border flex flex-col gap-2 rounded-lg border p-4 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="grid gap-0.5">
                        <p className="flex items-center gap-2 text-sm font-medium">
                          {contact.displayName}
                          {contact.isPrimary ? (
                            <Badge variant="secondary">Primary</Badge>
                          ) : null}
                        </p>
                        <p className="text-muted-foreground text-xs">
                          {contact.assignmentTypeLabel} · {contact.email}
                          {contact.isCurrent ? "" : " · Not current"}
                        </p>
                        <p className="text-muted-foreground text-xs">
                          {contact.startsAt || "Open"} → {contact.endsAt || "Open"}
                        </p>
                      </div>
                      <form
                        method="post"
                        action={routes.admin_office_contact_end(office.id)}
                      >
                        <input
                          type="hidden"
                          name="csrfmiddlewaretoken"
                          value={csrfToken}
                        />
                        <input type="hidden" name="expected_version" value={version} />
                        <input type="hidden" name="assignment" value={contact.id} />
                        <Button type="submit" variant="outline" size="sm">
                          End
                        </Button>
                      </form>
                    </li>
                  ))}
                </ul>
              )}

              <form
                method="post"
                action={routes.admin_office_contact(office.id)}
                className="grid gap-4 border-t pt-4 sm:grid-cols-2"
              >
                <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
                <input type="hidden" name="expected_version" value={version} />
                <FormField>
                  <FormLabel>Type</FormLabel>
                  <input type="hidden" name="assignment_type" value={contactType} />
                  <Select value={contactType} onValueChange={setContactType}>
                    <SelectTrigger aria-label="Contact type">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {administration.contactTypes.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FormField>
                <FormField>
                  <FormLabel>Person</FormLabel>
                  <input type="hidden" name="user" value={contactUserId} />
                  <Select
                    value={contactUserId}
                    onValueChange={setContactUserId}
                    disabled={!administration.contactCandidates.length}
                  >
                    <SelectTrigger aria-label="Contact person">
                      <SelectValue placeholder="Select a person" />
                    </SelectTrigger>
                    <SelectContent>
                      {administration.contactCandidates.map((candidate) => (
                        <SelectItem key={candidate.id} value={String(candidate.id)}>
                          {candidate.displayName}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FormField>
                <FormField>
                  <FormLabel htmlFor="starts_at">Starts</FormLabel>
                  <Input id="starts_at" name="starts_at" type="date" />
                </FormField>
                <FormField>
                  <FormLabel htmlFor="ends_at">Ends</FormLabel>
                  <Input id="ends_at" name="ends_at" type="date" />
                </FormField>
                <div className="flex items-center gap-2 text-sm sm:col-span-2">
                  <Checkbox
                    id="is_primary"
                    checked={contactPrimary}
                    onCheckedChange={(checked) => setContactPrimary(checked === true)}
                  />
                  <input
                    type="hidden"
                    name="is_primary"
                    value={contactPrimary ? "on" : ""}
                  />
                  <label htmlFor="is_primary">Primary for this type</label>
                </div>
                <div className="sm:col-span-2">
                  <Button
                    type="submit"
                    disabled={!contactUserId || submitting}
                    variant="secondary"
                  >
                    Add or update contact
                  </Button>
                </div>
              </form>
            </SurfaceCardContent>
          </SurfaceCard>

          {capabilities.canRestructure ? (
            <form
              ref={structureFormRef}
              method="post"
              action={routes.admin_office_structure(office.id)}
              className="grid gap-6"
              onSubmit={(event) => {
                event.preventDefault();
                const changes: AccessChange[] = [];
                if (parentId !== String(office.parentId ?? "")) {
                  const parent = administration.parentOptions.find(
                    (item) => String(item.id) === parentId,
                  );
                  changes.push({
                    label: "Parent",
                    from: office.parentPathLabel ?? "—",
                    to: parent?.pathLabel ?? parentId,
                    impact:
                      "Moves this office in the tree and refreshes region denormalization on descendants.",
                  });
                }
                if (kind !== office.kind) {
                  changes.push({
                    label: "Kind",
                    from: office.kindLabel,
                    to:
                      administration.kindOptions.find((item) => item.value === kind)
                        ?.label ?? kind,
                    impact: "Changes where this node may sit in the org tree.",
                  });
                }
                if (isActive !== office.isActive) {
                  changes.push({
                    label: "Active",
                    from: office.isActive ? "Active" : "Inactive",
                    to: isActive ? "Active" : "Inactive",
                    impact:
                      "Affects users, memberships, role grants, and contacts that reference this office.",
                  });
                }
                if (isAssignable !== office.isAssignable) {
                  changes.push({
                    label: "Assignable",
                    from: office.isAssignable ? "Yes" : "No",
                    to: isAssignable ? "Yes" : "No",
                    impact:
                      "Controls whether agents can pick this office as a workplace.",
                  });
                }
                if (changes.length) {
                  setStructureImpact(changes);
                  setConfirming(true);
                  return;
                }
                submitStructure(false);
              }}
            >
              <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
              <input type="hidden" name="expected_version" value={version} />
              <input type="hidden" name="parent" value={parentId} />
              <input type="hidden" name="kind" value={kind} />
              <input type="hidden" name="is_active" value={isActive ? "on" : ""} />
              <input
                type="hidden"
                name="is_assignable"
                value={isAssignable ? "on" : ""}
              />

              <SurfaceCard>
                <PanelHeader
                  divided
                  title="Hierarchy and status"
                  description="High-impact. Requires confirmation and company-wide authority."
                />
                <SurfaceCardContent className="grid gap-4 sm:grid-cols-2">
                  <FormField>
                    <FormLabel>Parent</FormLabel>
                    <Select value={parentId} onValueChange={setParentId}>
                      <SelectTrigger aria-label="Parent office">
                        <SelectValue placeholder="Select parent" />
                      </SelectTrigger>
                      <SelectContent>
                        {administration.parentOptions.map((option) => (
                          <SelectItem key={option.id} value={String(option.id)}>
                            {option.pathLabel}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </FormField>
                  <FormField>
                    <FormLabel>Kind</FormLabel>
                    <Select value={kind} onValueChange={setKind}>
                      <SelectTrigger aria-label="Office kind">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {administration.kindOptions.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </FormField>
                  <div className="flex items-center gap-2 text-sm">
                    <Checkbox
                      id="is_active"
                      checked={isActive}
                      onCheckedChange={(checked) => setIsActive(checked === true)}
                    />
                    <label htmlFor="is_active">Active</label>
                  </div>
                  <div className="flex items-center gap-2 text-sm">
                    <Checkbox
                      id="is_assignable"
                      checked={isAssignable}
                      onCheckedChange={(checked) => setIsAssignable(checked === true)}
                    />
                    <label htmlFor="is_assignable">Assignable workplace</label>
                  </div>
                </SurfaceCardContent>
              </SurfaceCard>

              <FormActionBar status="High-impact changes require confirmation.">
                <Button type="submit" variant="secondary" disabled={submitting}>
                  Apply structure changes
                </Button>
              </FormActionBar>
            </form>
          ) : null}
        </div>

        <aside className="grid content-start gap-6">
          <SurfaceCard>
            <PanelHeader title="Related resources" />
            <SurfaceCardContent className="grid gap-3">
              {resourceLinks.map((link) => (
                <div key={link.key} className="grid gap-1">
                  {link.available ? (
                    <Link
                      href={link.href}
                      className="text-primary inline-flex items-center gap-1.5 text-sm font-medium underline-offset-2 hover:underline"
                    >
                      {link.label}
                      <ExternalLink className="size-3.5" aria-hidden />
                    </Link>
                  ) : (
                    <span className="text-muted-foreground text-sm font-medium">
                      {link.label} · Soon
                    </span>
                  )}
                  <p className="text-muted-foreground text-xs">
                    {link.description}
                    {link.note ? ` ${link.note}` : ""}
                  </p>
                </div>
              ))}
            </SurfaceCardContent>
          </SurfaceCard>

          <div className="grid gap-3">
            <h2 className="text-foreground text-sm font-semibold">Agent preview</h2>
            <OfficeInfoPanel info={agentPreview} preview />
          </div>
        </aside>
      </div>

      <AccessChangeDialog
        open={confirming}
        onOpenChange={setConfirming}
        title="Confirm high-impact office change"
        description="Review who and what this change affects before it is saved."
        changes={structureImpact}
        confirmLabel="Confirm and save"
        submitting={submitting}
        onConfirm={() => {
          setConfirming(false);
          submitStructure(true);
        }}
      />
    </div>
  );
}

export default function OfficeAdministrationDetail() {
  return (
    <PermissionRequired permission={MANAGE}>
      <OfficeAdministrationDetailPage />
    </PermissionRequired>
  );
}

OfficeAdministrationDetail.layout = (props: OfficeAdministrationDetailPageProps) =>
  [
    HubLayout,
    {
      context: {
        title: props.administration.office.name,
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Offices", href: routes.admin_offices() },
          { label: props.administration.office.name },
        ],
        back: { label: "Back to offices", href: routes.admin_offices() },
      },
    },
  ] as const;
