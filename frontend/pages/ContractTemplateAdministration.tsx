import { Head, Link, router, usePage } from "@inertiajs/react";
import { BadgeCheck, Building2, FileText, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import {
  CreateSheet,
  DataTable,
  FormErrorSummary,
  FormFieldError,
  fieldA11yProps,
  PageHeader,
  PanelHeader,
  SearchControl,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { StateMultiSelect } from "@/components/StateMultiSelect";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { routes } from "@/lib/routes";
import { firstFieldError } from "@/lib/validation";
import type { ContractTemplateAdministrationPageProps } from "@/types";

const ACCESS = {
  any: ["contract.manage_contract_templates", "contract.approve_contract_templates"],
};

export default function ContractTemplateAdministration() {
  const { templates, capabilities, createSheet, errors, states } =
    usePage<ContractTemplateAdministrationPageProps>().props;
  const [createOpen, setCreateOpen] = useState(Boolean(createSheet?.open));
  const [query, setQuery] = useState(templates.filters.q ?? "");
  const rows = templates.items;
  const total = templates.pagination.totalItems;
  const draftJurisdiction = Array.isArray(createSheet?.draft?.jurisdiction_state_codes)
    ? (createSheet?.draft?.jurisdiction_state_codes as string[])
    : typeof createSheet?.draft?.jurisdiction_state_codes === "string"
      ? String(createSheet.draft.jurisdiction_state_codes)
          .split(",")
          .map((part) => part.trim())
          .filter(Boolean)
      : [];
  const activeFilters = useMemo(
    () =>
      [templates.filters.status, templates.filters.jurisdiction].filter(Boolean)
        .length + (query ? 1 : 0),
    [query, templates.filters.jurisdiction, templates.filters.status],
  );

  function visit(patch: Record<string, string>) {
    router.get(
      routes.admin_contract_templates(),
      {
        q: query,
        status: templates.filters.status,
        jurisdiction: templates.filters.jurisdiction,
        ...patch,
      },
      { preserveScroll: true, preserveState: true, replace: true },
    );
  }

  return (
    <PermissionRequired permission={ACCESS}>
      <div className="grid gap-8">
        <Head title="Contract Templates" />
        <PageHeader
          title="Contract Templates"
          description="Govern approved brokerage agreement templates, merge variables, immutable versions, previews, and office applicability."
          actions={
            capabilities.canManage ? (
              <Button type="button" onClick={() => setCreateOpen(true)}>
                <Plus className="size-4" aria-hidden />
                New template
              </Button>
            ) : null
          }
        />
        <FormErrorSummary errors={errors} />

        <CreateSheet
          open={createOpen}
          onOpenChange={setCreateOpen}
          title="New contract template"
          description="Create the template family and its first draft version. Publishing and activation happen later in the workspace."
          action={routes.contract_template_create()}
          csrfToken={usePage().props.csrfToken as string}
          formId="contract-template-create-form"
          submitLabel="Create draft"
        >
          <div className="grid gap-4" id="contract-template-create-form">
            <div className="grid gap-2">
              <Label htmlFor="stable_key">Stable key</Label>
              <Input
                id="stable_key"
                name="stable_key"
                required
                defaultValue={String(createSheet?.draft?.stable_key ?? "")}
                {...fieldA11yProps("stable_key", errors)}
              />
              <FormFieldError message={firstFieldError(errors, "stable_key")} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="name">Display name</Label>
              <Input
                id="name"
                name="name"
                required
                defaultValue={String(createSheet?.draft?.name ?? "")}
                {...fieldA11yProps("name", errors)}
              />
              <FormFieldError message={firstFieldError(errors, "name")} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="version_label">Initial version</Label>
              <Input
                id="version_label"
                name="version_label"
                defaultValue={String(createSheet?.draft?.version_label ?? "1.0.0")}
                required
                {...fieldA11yProps("version_label", errors)}
              />
              <FormFieldError message={firstFieldError(errors, "version_label")} />
            </div>
            <StateMultiSelect
              id="jurisdiction_state_codes"
              name="jurisdiction_state_codes"
              label="Jurisdiction states"
              options={states ?? []}
              defaultValue={draftJurisdiction}
              placeholder="Select states (optional)"
              hint="Leave empty for all jurisdictions. Matching agent offices must use one of these states."
            />
            <div className="grid gap-2">
              <Label htmlFor="description">Description</Label>
              <Textarea
                id="description"
                name="description"
                rows={4}
                defaultValue={String(createSheet?.draft?.description ?? "")}
                {...fieldA11yProps("description", errors)}
              />
              <FormFieldError message={firstFieldError(errors, "description")} />
            </div>
            <label
              className="flex items-center gap-2 text-sm font-medium"
              htmlFor="company_wide"
            >
              <Checkbox
                id="company_wide"
                name="company_wide"
                value="on"
                defaultChecked={
                  createSheet?.draft?.company_wide === "on" ||
                  createSheet?.draft?.company_wide === true
                }
              />
              Company-wide applicability
            </label>
          </div>
        </CreateSheet>

        <SurfaceCard>
          <PanelHeader
            title="Template families"
            description="Drafts and published versions in your scope."
            meta={
              <span className="text-muted-foreground text-xs font-medium">
                {total} template{total === 1 ? "" : "s"}
                {activeFilters
                  ? ` · ${activeFilters} active filter${activeFilters === 1 ? "" : "s"}`
                  : ""}
              </span>
            }
          />
          <SurfaceCardContent className="grid gap-4">
            <SearchControl
              label="Search templates"
              value={query}
              onValueChange={setQuery}
              onSearch={(next) => visit({ q: next })}
              onClear={() => {
                setQuery("");
                visit({ q: "" });
              }}
              placeholder="Name or stable key"
              className="max-w-xl"
            />
            <DataTable
              frame="bleed"
              caption="Contract templates"
              rows={rows}
              rowKey={(row) => row.publicId}
              emptyTitle="No templates yet"
              emptyDescription="Create a governed draft template to start the approval workflow."
              columns={[
                {
                  id: "name",
                  header: "Template",
                  icon: FileText,
                  cell: (row) => (
                    <div className="grid gap-0.5">
                      <span className="font-semibold">{row.name}</span>
                      <span className="text-muted-foreground text-xs">
                        {row.stableKey} ·{" "}
                        {row.jurisdictionStateCodes.join(", ") || "No states"}
                      </span>
                    </div>
                  ),
                },
                {
                  id: "scope",
                  header: "Scope",
                  icon: Building2,
                  cell: (row) => (
                    <span className="text-sm">
                      {row.companyWide ? "Company-wide" : "Scoped"}
                    </span>
                  ),
                },
                {
                  id: "status",
                  header: "Status",
                  icon: BadgeCheck,
                  cell: (row) => (
                    <span className="text-sm capitalize">{row.status}</span>
                  ),
                },
                {
                  id: "actions",
                  header: <span className="sr-only">Actions</span>,
                  cell: (row) =>
                    row.workspaceVersionPk ? (
                      <Button asChild variant="outline" size="sm">
                        <Link
                          href={routes.contract_template_workspace(
                            row.workspaceVersionPk,
                          )}
                        >
                          {row.activeVersionPk &&
                          row.workspaceVersionPk === row.activeVersionPk
                            ? "Open"
                            : "Edit draft"}
                        </Link>
                      </Button>
                    ) : (
                      <span className="text-muted-foreground text-xs">
                        No version yet
                      </span>
                    ),
                  className: "text-right",
                  headerClassName: "text-right",
                },
              ]}
            />
          </SurfaceCardContent>
        </SurfaceCard>
      </div>
    </PermissionRequired>
  );
}

ContractTemplateAdministration.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Contract Templates",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Contract Templates", href: routes.admin_contract_templates() },
        ],
      },
      variant: "standard",
    },
  ] as const;
