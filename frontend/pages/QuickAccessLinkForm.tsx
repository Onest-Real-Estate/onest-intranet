import { Head, Link, router, usePage } from "@inertiajs/react";
import { type FormEvent, useMemo, useState } from "react";

import { AccessChangeDialog } from "@/components/administration/AccessChangeDialog";
import {
  FormActionBar,
  FormDescription,
  FormErrorSummary,
  FormField,
  FormFieldError,
  FormLabel,
  fieldA11yProps,
  PageHeader,
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
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
import { routes } from "@/lib/routes";
import { firstFieldError } from "@/lib/validation";
import type { QuickAccessExposureChange, QuickAccessLinkFormPageProps } from "@/types";

const MANAGE = { all: ["web.manage_quick_access"] };

const FIELD_LABELS: Record<string, string> = {
  stable_key: "Stable key",
  name: "Name",
  description: "Description",
  destination_type: "Destination type",
  destination_value: "Destination",
  icon: "Icon",
  sort_order: "Position",
  publish_start_at: "Publish from",
  publish_end_at: "Publish until",
  roles: "Role audience",
  offices: "Office audience",
  company_wide: "Company-wide",
};

interface DraftState {
  stableKey: string;
  name: string;
  description: string;
  destinationType: string;
  destinationValue: string;
  icon: string;
  sortOrder: string;
  publishStartAt: string;
  publishEndAt: string;
  sso: string;
  health: string;
  setup: string;
  isActive: boolean;
  companyWide: boolean;
  roles: string[];
  offices: number[];
}

function localDateTime(value: string | null): string {
  if (!value) {
    return "";
  }
  // `datetime-local` wants `YYYY-MM-DDTHH:mm` with no zone suffix.
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/**
 * Create or edit one Quick Access link.
 *
 * Two rules from the server are mirrored here so the person using the form is
 * not surprised by a rejection: the audience picker only offers offices inside
 * the administrator's scope, and a widening change routes through a
 * confirmation before it is submitted. Neither is load-bearing — the server
 * refuses the same things whatever this page renders.
 */
function QuickAccessLinkFormPage() {
  const {
    link,
    errors,
    pendingConfirmation,
    iconOptions,
    internalDestinations,
    destinationTypeOptions,
    ssoOptions,
    healthOptions,
    setupOptions,
    roleOptions,
    officeOptions,
    capabilities,
  } = usePage<QuickAccessLinkFormPageProps>().props;

  const editing = link !== null;
  const [draft, setDraft] = useState<DraftState>(() => ({
    stableKey: link?.stableKey ?? "",
    name: link?.name ?? "",
    description: link?.description ?? "",
    destinationType: link?.destinationType ?? "external_url",
    destinationValue: link?.destinationValue ?? "",
    icon: link?.icon ?? "app-window",
    sortOrder: String(link?.sortOrder ?? 0),
    publishStartAt: localDateTime(link?.publishStartAt ?? null),
    publishEndAt: localDateTime(link?.publishEndAt ?? null),
    sso: link?.ssoCapability ?? "none",
    health: link?.integrationHealth ?? "unknown",
    setup: link?.setupBehavior ?? "self_service",
    isActive: link?.isActive ?? true,
    companyWide: link?.audience.companyWide ?? false,
    roles: link?.audience.roles.map((role) => role.code) ?? [],
    offices: link?.audience.offices.map((office) => office.id) ?? [],
  }));
  const [confirming, setConfirming] =
    useState<QuickAccessExposureChange[]>(pendingConfirmation);
  const [submitting, setSubmitting] = useState(false);

  const original = useMemo(
    () => ({
      companyWide: link?.audience.companyWide ?? false,
      offices: new Set(link?.audience.offices.map((office) => office.id) ?? []),
      roles: link?.audience.roles.map((role) => role.code) ?? [],
      destination: link?.destinationValue ?? "",
    }),
    [link],
  );

  /**
   * The same widening test the server runs, for the sake of asking first.
   * A narrowing change — fewer offices, a tighter role filter — needs no
   * confirmation, because taking access away is not the risky direction.
   */
  function exposureChanges(): QuickAccessExposureChange[] {
    if (!editing) {
      return [
        {
          label: "New link",
          from: "Not published",
          to: draft.companyWide ? "Every office" : `${draft.offices.length} office(s)`,
          impact: "Everyone in this audience gets the launcher on their dashboard.",
        },
      ];
    }
    const changes: QuickAccessExposureChange[] = [];
    if (draft.destinationValue !== original.destination) {
      changes.push({
        label: "Destination",
        from: original.destination,
        to: draft.destinationValue,
        impact: "Everyone who can see this link goes somewhere new.",
      });
    }
    if (draft.companyWide && !original.companyWide) {
      changes.push({
        label: "Audience",
        from: "Selected offices",
        to: "Every office in the brokerage",
        impact: "The link becomes visible brokerage-wide.",
      });
    }
    const added = draft.offices.filter((id) => !original.offices.has(id));
    if (added.length > 0) {
      changes.push({
        label: "Offices added",
        from: `${original.offices.size} office(s)`,
        to: `${draft.offices.length} office(s)`,
        impact: "People in these offices can now see the link.",
      });
    }
    const removedRoles = original.roles.filter((code) => !draft.roles.includes(code));
    if (removedRoles.length > 0) {
      changes.push({
        label: "Role audience widened",
        from: original.roles.join(", "),
        to: draft.roles.length === 0 ? "Every role" : draft.roles.join(", "),
        impact: "Roles were removed from the filter, widening who sees it.",
      });
    }
    return changes;
  }

  function submit(acknowledged: boolean) {
    setSubmitting(true);
    const payload: Record<string, string | string[] | number[]> = {
      stable_key: draft.stableKey,
      name: draft.name,
      description: draft.description,
      destination_type: draft.destinationType,
      destination_value: draft.destinationValue,
      icon: draft.icon,
      sort_order: draft.sortOrder,
      publish_start_at: draft.publishStartAt,
      publish_end_at: draft.publishEndAt,
      sso_capability: draft.sso,
      integration_health: draft.health,
      setup_behavior: draft.setup,
      roles: draft.roles,
      offices: draft.offices.map(String),
      expected_version: link?.version ?? "",
    };
    if (draft.isActive) {
      payload.is_active = "on";
    }
    if (draft.companyWide) {
      payload.company_wide = "on";
    }
    if (acknowledged) {
      payload.acknowledge_exposure = "on";
    }
    router.post(
      editing ? routes.quick_access_update(link.id) : routes.quick_access_create(),
      payload,
      { onFinish: () => setSubmitting(false) },
    );
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const changes = exposureChanges();
    if (changes.length > 0) {
      setConfirming(changes);
      return;
    }
    submit(false);
  }

  const isInternal = draft.destinationType === "internal_route";

  return (
    <div className="grid max-w-4xl gap-8">
      <Head title={editing ? `Edit ${link.name}` : "New Quick Access link"} />
      <PageHeader
        title={editing ? link.name : "New Quick Access link"}
        description="A launcher on every dashboard in its audience. Destinations must be https, or one of the approved in-app pages."
      />

      <FormErrorSummary errors={errors} labels={FIELD_LABELS} />

      <form className="grid gap-8" onSubmit={onSubmit} noValidate>
        <SurfaceCard>
          <PanelHeader divided title="The tool" />
          <SurfaceCardContent className="grid gap-5 sm:grid-cols-2">
            <FormField>
              <FormLabel htmlFor="name" required>
                Name
              </FormLabel>
              <Input
                id="name"
                value={draft.name}
                onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                {...fieldA11yProps("name", errors)}
              />
              <FormFieldError message={firstFieldError(errors, "name")} />
            </FormField>

            <FormField>
              <FormLabel htmlFor="stable_key" required>
                Stable key
              </FormLabel>
              <Input
                id="stable_key"
                value={draft.stableKey}
                disabled={editing}
                onChange={(event) =>
                  setDraft({ ...draft, stableKey: event.target.value })
                }
                {...fieldA11yProps("stable_key", errors, "stable_key_help")}
              />
              <FormDescription id="stable_key_help">
                Permanent identity used by audit records. It cannot be changed later.
              </FormDescription>
              <FormFieldError message={firstFieldError(errors, "stable_key")} />
            </FormField>

            <FormField className="sm:col-span-2">
              <FormLabel htmlFor="description" optional>
                Description
              </FormLabel>
              <Input
                id="description"
                value={draft.description}
                onChange={(event) =>
                  setDraft({ ...draft, description: event.target.value })
                }
                {...fieldA11yProps("description", errors)}
              />
              <FormFieldError message={firstFieldError(errors, "description")} />
            </FormField>

            <FormField>
              <FormLabel htmlFor="icon" required>
                Icon
              </FormLabel>
              <Select
                value={draft.icon}
                onValueChange={(value) => setDraft({ ...draft, icon: value })}
              >
                <SelectTrigger id="icon">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {iconOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormFieldError message={firstFieldError(errors, "icon")} />
            </FormField>

            <FormField>
              <FormLabel htmlFor="sort_order">Position</FormLabel>
              <Input
                id="sort_order"
                type="number"
                min={0}
                value={draft.sortOrder}
                onChange={(event) =>
                  setDraft({ ...draft, sortOrder: event.target.value })
                }
                {...fieldA11yProps("sort_order", errors, "sort_order_help")}
              />
              <FormDescription id="sort_order_help">
                Lower sorts first. Positions may repeat — reorder from the list instead
                of renumbering by hand.
              </FormDescription>
              <FormFieldError message={firstFieldError(errors, "sort_order")} />
            </FormField>
          </SurfaceCardContent>
        </SurfaceCard>

        <SurfaceCard>
          <PanelHeader
            divided
            title="Destination"
            description="External links must be https. Internal links point at an approved page by name, never a typed path."
          />
          <SurfaceCardContent className="grid gap-5 sm:grid-cols-2">
            <FormField>
              <FormLabel htmlFor="destination_type" required>
                Destination type
              </FormLabel>
              <Select
                value={draft.destinationType}
                onValueChange={(value) =>
                  setDraft({ ...draft, destinationType: value, destinationValue: "" })
                }
              >
                <SelectTrigger id="destination_type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {destinationTypeOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FormField>

            <FormField>
              <FormLabel htmlFor="destination_value" required>
                Destination
              </FormLabel>
              {isInternal ? (
                <Select
                  value={draft.destinationValue || undefined}
                  onValueChange={(value) =>
                    setDraft({ ...draft, destinationValue: value })
                  }
                >
                  <SelectTrigger id="destination_value">
                    <SelectValue placeholder="Choose a page" />
                  </SelectTrigger>
                  <SelectContent>
                    {internalDestinations.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <Input
                  id="destination_value"
                  inputMode="url"
                  placeholder="https://"
                  value={draft.destinationValue}
                  onChange={(event) =>
                    setDraft({ ...draft, destinationValue: event.target.value })
                  }
                  {...fieldA11yProps("destination_value", errors, "destination_help")}
                />
              )}
              <FormDescription id="destination_help">
                Never include a token, key, or password. Sign-in secrets belong in the
                identity provider.
              </FormDescription>
              <FormFieldError message={firstFieldError(errors, "destination_value")} />
            </FormField>
          </SurfaceCardContent>
        </SurfaceCard>

        <SurfaceCard>
          <PanelHeader
            divided
            title="Audience"
            description="Who sees this link. Roles and offices are ANDed: a link limited to Realtor in two offices reaches realtors in those two offices."
          />
          <SurfaceCardContent className="grid gap-5">
            <FormField>
              <div className="flex items-start gap-3 text-sm">
                <Checkbox
                  id="company_wide"
                  checked={draft.companyWide}
                  disabled={!capabilities.companyWide}
                  onCheckedChange={(checked) =>
                    setDraft({ ...draft, companyWide: checked === true })
                  }
                  aria-describedby="company_wide_help"
                />
                <div className="grid gap-1">
                  <label htmlFor="company_wide" className="font-medium">
                    Publish company-wide
                  </label>
                  <span
                    className="text-muted-foreground text-xs"
                    id="company_wide_help"
                  >
                    {capabilities.companyWide
                      ? "Ignores the office list and shows this to every office."
                      : "Your role cannot publish brokerage-wide."}
                  </span>
                </div>
              </div>
              <FormFieldError message={firstFieldError(errors, "company_wide")} />
            </FormField>

            {/* A fieldset, not a labelled div: a set of related checkboxes is
                exactly what a legend names, and screen readers announce it on
                entry rather than only on the first box. */}
            <fieldset className="grid min-w-0 gap-2">
              <legend className="text-xs font-semibold tracking-[0.02em]">
                Role audience
              </legend>
              <FormDescription id="roles_help">
                Leave every box clear to show this link to every role.
              </FormDescription>
              <div className="grid gap-2 sm:grid-cols-2">
                {roleOptions.map((option) => (
                  <div key={option.value} className="flex items-center gap-2 text-sm">
                    <Checkbox
                      id={`role_${option.value}`}
                      aria-describedby="roles_help"
                      checked={draft.roles.includes(option.value)}
                      onCheckedChange={(checked) =>
                        setDraft({
                          ...draft,
                          roles:
                            checked === true
                              ? [...draft.roles, option.value]
                              : draft.roles.filter((code) => code !== option.value),
                        })
                      }
                    />
                    <label htmlFor={`role_${option.value}`}>{option.label}</label>
                  </div>
                ))}
              </div>
              <FormFieldError message={firstFieldError(errors, "roles")} />
            </fieldset>

            <fieldset className="grid min-w-0 gap-2">
              <legend className="text-xs font-semibold tracking-[0.02em]">
                Office audience
              </legend>
              <FormDescription id="offices_help">
                Only offices inside your own scope are listed. A region covers the
                offices beneath it.
              </FormDescription>
              <div className="max-h-64 overflow-y-auto rounded-lg border p-3">
                <div className="grid gap-2">
                  {officeOptions.map((option) => (
                    <div key={option.value} className="flex items-center gap-2 text-sm">
                      <Checkbox
                        id={`office_${option.value}`}
                        aria-describedby="offices_help"
                        checked={draft.offices.includes(option.value)}
                        disabled={draft.companyWide}
                        onCheckedChange={(checked) =>
                          setDraft({
                            ...draft,
                            offices:
                              checked === true
                                ? [...draft.offices, option.value]
                                : draft.offices.filter((id) => id !== option.value),
                          })
                        }
                      />
                      <label htmlFor={`office_${option.value}`}>{option.label}</label>
                    </div>
                  ))}
                </div>
              </div>
              <FormFieldError message={firstFieldError(errors, "offices")} />
            </fieldset>
          </SurfaceCardContent>
        </SurfaceCard>

        <SurfaceCard>
          <PanelHeader
            divided
            title="Availability and integration"
            description="The publish window and the operational facts onboarding reads later."
          />
          <SurfaceCardContent className="grid gap-5 sm:grid-cols-2">
            <FormField>
              <FormLabel htmlFor="publish_start_at" optional>
                Publish from
              </FormLabel>
              <Input
                id="publish_start_at"
                type="datetime-local"
                value={draft.publishStartAt}
                onChange={(event) =>
                  setDraft({ ...draft, publishStartAt: event.target.value })
                }
                {...fieldA11yProps("publish_start_at", errors)}
              />
              <FormFieldError message={firstFieldError(errors, "publish_start_at")} />
            </FormField>

            <FormField>
              <FormLabel htmlFor="publish_end_at" optional>
                Publish until
              </FormLabel>
              <Input
                id="publish_end_at"
                type="datetime-local"
                value={draft.publishEndAt}
                onChange={(event) =>
                  setDraft({ ...draft, publishEndAt: event.target.value })
                }
                {...fieldA11yProps("publish_end_at", errors)}
              />
              <FormFieldError message={firstFieldError(errors, "publish_end_at")} />
            </FormField>

            <FormField>
              <FormLabel htmlFor="sso_capability">Single sign-on</FormLabel>
              <Select
                value={draft.sso}
                onValueChange={(value) => setDraft({ ...draft, sso: value })}
              >
                <SelectTrigger id="sso_capability">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ssoOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FormField>

            <FormField>
              <FormLabel htmlFor="integration_health">Integration health</FormLabel>
              <Select
                value={draft.health}
                onValueChange={(value) => setDraft({ ...draft, health: value })}
              >
                <SelectTrigger id="integration_health">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {healthOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FormField>

            <FormField>
              <FormLabel htmlFor="setup_behavior">Setup behaviour</FormLabel>
              <Select
                value={draft.setup}
                onValueChange={(value) => setDraft({ ...draft, setup: value })}
              >
                <SelectTrigger id="setup_behavior">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {setupOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FormField>

            <FormField>
              <div className="flex items-center gap-3 text-sm">
                <Checkbox
                  id="is_active"
                  checked={draft.isActive}
                  onCheckedChange={(checked) =>
                    setDraft({ ...draft, isActive: checked === true })
                  }
                />
                <label htmlFor="is_active" className="font-medium">
                  Active
                </label>
              </div>
            </FormField>
          </SurfaceCardContent>
        </SurfaceCard>

        <FormActionBar
          status={
            submitting
              ? "Saving your changes…"
              : editing
                ? "Changes apply to every office that shows this link."
                : "The link goes live as soon as you create it."
          }
        >
          <Button
            type="submit"
            disabled={submitting}
            aria-busy={submitting || undefined}
          >
            {submitting ? "Saving…" : editing ? "Save changes" : "Create link"}
          </Button>
          <Button type="button" variant="outline" asChild>
            <Link href={routes.admin_quick_access()}>Cancel</Link>
          </Button>
        </FormActionBar>
      </form>

      <AccessChangeDialog
        open={confirming.length > 0}
        onOpenChange={(open) => {
          if (!open) {
            setConfirming([]);
          }
        }}
        title="This change widens who can see the tool"
        description="Check the new audience and destination before it reaches anybody's dashboard."
        changes={confirming}
        confirmLabel="Publish the change"
        submitting={submitting}
        onConfirm={() => {
          setConfirming([]);
          submit(true);
        }}
      />
    </div>
  );
}

export default function QuickAccessLinkForm() {
  return (
    <PermissionRequired permission={MANAGE}>
      <QuickAccessLinkFormPage />
    </PermissionRequired>
  );
}

QuickAccessLinkForm.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Quick Access",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Quick Access", href: routes.admin_quick_access() },
        ],
      },
      variant: "standard",
    },
  ] as const;
