import { Head, Link, router, usePage } from "@inertiajs/react";
import { Plus } from "lucide-react";
import { useMemo, useState } from "react";
import {
  CreateSheet,
  DataTable,
  FormErrorSummary,
  PageHeader,
  PanelHeader,
  SearchControl,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { routes } from "@/lib/routes";
import type { ContractTemplateAdministrationPageProps } from "@/types";

const ACCESS = {
  any: ["contract.manage_contract_templates", "contract.approve_contract_templates"],
};

export default function ContractTemplateAdministration() {
  const { templates, capabilities, createSheet, errors } =
    usePage<ContractTemplateAdministrationPageProps>().props;
  const [createOpen, setCreateOpen] = useState(Boolean(createSheet?.open));
  const [query, setQuery] = useState(templates.filters.q ?? "");
  const rows = templates.items;
  const total = templates.pagination.totalItems;
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
              <Input id="stable_key" name="stable_key" required />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="name">Display name</Label>
              <Input id="name" name="name" required />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="version_label">Initial version</Label>
              <Input
                id="version_label"
                name="version_label"
                defaultValue="1.0.0"
                required
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="jurisdiction_state_codes">Jurisdiction states</Label>
              <Input
                id="jurisdiction_state_codes"
                name="jurisdiction_state_codes"
                placeholder="VA, MD"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="description">Description</Label>
              <Textarea id="description" name="description" rows={4} />
            </div>
            <label
              className="flex items-center gap-2 text-sm font-medium"
              htmlFor="company_wide"
            >
              <Checkbox id="company_wide" name="company_wide" value="on" />
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
                  cell: (row) => (
                    <span className="text-sm">
                      {row.companyWide ? "Company-wide" : "Scoped"}
                    </span>
                  ),
                },
                {
                  id: "status",
                  header: "Status",
                  cell: (row) => (
                    <span className="text-sm capitalize">{row.status}</span>
                  ),
                },
                {
                  id: "actions",
                  header: <span className="sr-only">Actions</span>,
                  cell: (row) =>
                    row.activeVersionPk ? (
                      <Button asChild variant="outline" size="sm">
                        <Link
                          href={routes.contract_template_workspace(row.activeVersionPk)}
                        >
                          Open
                        </Link>
                      </Button>
                    ) : (
                      <span className="text-muted-foreground text-xs">
                        No active version
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
