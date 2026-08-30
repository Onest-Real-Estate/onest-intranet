import { Head, Link, router, usePage } from "@inertiajs/react";
import { ArrowRight, BadgeCheck, CalendarClock, FileText, Tag } from "lucide-react";
import { useState } from "react";

import {
  CreateSheet,
  DataTable,
  FilterControls,
  FilterField,
  PageHeader,
  Pagination,
  SearchControl,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { ResourceFormFields } from "@/components/office/ResourceFormFields";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { buildListUrl } from "@/lib/list-query";
import { routes } from "@/lib/routes";
import { hasValidationErrors } from "@/lib/validation";
import type {
  AdminOfficeResourceRow,
  FilterOption,
  OfficeResourceListFilters,
  OfficeResourcesAdministrationPageProps,
} from "@/types";

const VIEW = { all: ["web.view_office_resources_admin"] };
const ALL = "__all__";

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: FilterOption[];
  onChange: (next: string) => void;
}) {
  return (
    <FilterField label={label} hideLabel>
      <Select
        value={value || ALL}
        onValueChange={(next) => onChange(next === ALL ? "" : next)}
      >
        <SelectTrigger size="sm" aria-label={label}>
          <SelectValue placeholder={`Any ${label.toLowerCase()}`} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>Any {label.toLowerCase()}</SelectItem>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </FilterField>
  );
}

const STATE_TONES: Record<
  AdminOfficeResourceRow["state"],
  { label: string; tone: "success" | "neutral" | "warning" | "destructive" }
> = {
  active: { label: "Active", tone: "success" },
  inactive: { label: "Inactive", tone: "neutral" },
  scheduled: { label: "Scheduled", tone: "warning" },
  expired: { label: "Expired", tone: "destructive" },
  archived: { label: "Archived", tone: "neutral" },
};

/**
 * Scoped administration console for the Office Resources catalog. Every row
 * shown already passed the server's grant-boundary filter — the page never
 * asks for a wider set. Creating happens in a right-side sheet so the list
 * stays in context; a failed create re-opens the sheet with inline errors.
 */
export default function OfficeResourcesAdministration() {
  const {
    resources,
    filterOptions,
    capabilities,
    scope,
    validation,
    createSheet,
    writableOffices,
    csrfToken,
  } = usePage<OfficeResourcesAdministrationPageProps>().props;
  const [query, setQuery] = useState(resources.filters.q ?? "");
  const [createOpen, setCreateOpen] = useState(
    Boolean(createSheet?.open) || hasValidationErrors(validation),
  );
  const filters = resources.filters as OfficeResourceListFilters;
  const draft = (createSheet?.draft ?? {}) as Record<string, string>;

  function visit(next: Partial<Record<string, string>>, page?: number) {
    const merged = { ...filters, ...next } as OfficeResourceListFilters;
    router.get(
      buildListUrl(routes.admin_office_resources(), window.location.search, {
        q: next.q !== undefined ? next.q : query,
        page,
        filters: merged,
      }),
      {},
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  const activeCount = (
    ["category", "resource_type", "status", "owner", "region"] as const
  ).filter((key) => Boolean(filters[key])).length;

  return (
    <PermissionRequired permission={VIEW}>
      <Head title="Office Resources" />
      <div className="grid gap-8">
        <PageHeader
          title="Office Resources"
          description="Publish instructions, procedures, contacts, links, and files to branches."
          meta={
            <span className="text-muted-foreground text-sm">
              {scope.label}
              {capabilities.canPublishCompany
                ? " · Company publishing"
                : capabilities.canManage
                  ? " · Scoped publishing"
                  : ""}
            </span>
          }
          actions={
            capabilities.canManage ? (
              <Button type="button" onClick={() => setCreateOpen(true)}>
                New resource
              </Button>
            ) : undefined
          }
        />

        {capabilities.canManage && createOpen ? (
          <CreateSheet
            open={createOpen}
            onOpenChange={setCreateOpen}
            title="New resource"
            description="Publish an instruction, link, or file to a branch in your scope."
            action={routes.admin_office_resource_create()}
            csrfToken={csrfToken}
            formId="office-resource-create-form"
            submitLabel="Create resource"
            // File resources upload their bytes with the create, so the drawer
            // carries a multipart form rather than a second endpoint.
            encType="multipart/form-data"
          >
            <ResourceFormFields
              defaults={draft}
              categories={filterOptions.categories}
              types={filterOptions.types}
              writableOffices={writableOffices}
              includeFile
            />
          </CreateSheet>
        ) : null}

        <SurfaceCard>
          <SurfaceCardContent className="grid gap-4">
            <FilterControls
              activeCount={activeCount + Number(Boolean(resources.filters.q))}
              onReset={() =>
                visit({
                  q: "",
                  category: "",
                  resource_type: "",
                  status: "",
                  owner: "",
                  region: "",
                })
              }
            >
              <SearchControl
                value={query}
                onValueChange={setQuery}
                onSearch={() => visit({ q: query }, 1)}
                placeholder="Search title, summary, or slug"
                className="min-w-56"
              />
              <FilterSelect
                label="Category"
                value={filters.category ?? ""}
                options={filterOptions.categories}
                onChange={(category) => visit({ category }, 1)}
              />
              <FilterSelect
                label="Type"
                value={filters.resource_type ?? ""}
                options={filterOptions.types}
                onChange={(resource_type) => visit({ resource_type }, 1)}
              />
              <FilterSelect
                label="State"
                value={filters.status ?? ""}
                options={filterOptions.statuses}
                onChange={(status) => visit({ status }, 1)}
              />
              <FilterSelect
                label="Owner"
                value={filters.owner ?? ""}
                options={filterOptions.owners}
                onChange={(owner) => visit({ owner }, 1)}
              />
            </FilterControls>

            <DataTable
              caption="Resources in your administrative scope"
              rows={resources.items}
              rowKey={(row) => String(row.id)}
              emptyTitle="No resources in scope"
              emptyDescription="Nothing matches these filters inside your administrative reach."
              columns={[
                {
                  id: "title",
                  header: "Resource",
                  icon: FileText,
                  cell: (row: AdminOfficeResourceRow) => (
                    <span className="grid min-w-0 gap-0.5">
                      <Link
                        href={routes.admin_office_resource(row.id)}
                        className="text-primary font-medium underline-offset-2 hover:underline"
                      >
                        {row.title}
                      </Link>
                      <span className="text-muted-foreground truncate text-xs">
                        /{row.slug} · {row.ownerPathLabel}
                      </span>
                    </span>
                  ),
                },
                {
                  id: "category",
                  header: "Category",
                  icon: Tag,
                  cell: (row) => row.categoryLabel,
                  hideBelow: "2xl",
                },
                {
                  id: "type",
                  header: "Type",
                  icon: Tag,
                  cell: (row) => row.typeLabel,
                  hideBelow: "4xl",
                },
                {
                  id: "schedule",
                  header: "Schedule",
                  icon: CalendarClock,
                  cell: (row: AdminOfficeResourceRow) =>
                    row.startsAt || row.endsAt
                      ? `${row.startsAt || "open"} → ${row.endsAt || "open"}`
                      : "—",
                  className: "tabular-nums",
                  headerClassName: "tabular-nums",
                  hideBelow: "5xl",
                },
                {
                  id: "state",
                  header: "State",
                  icon: BadgeCheck,
                  cell: (row: AdminOfficeResourceRow) => (
                    <span className="flex flex-wrap items-center gap-1.5">
                      <StatusBadge status={STATE_TONES[row.state]} />
                      {row.processingState === "quarantined" ? (
                        <StatusBadge
                          status={{
                            label: "File quarantined",
                            tone: "destructive",
                          }}
                        />
                      ) : null}
                    </span>
                  ),
                },
                {
                  id: "open",
                  header: <span className="sr-only">Open</span>,
                  cell: (row: AdminOfficeResourceRow) =>
                    capabilities.canManage ? (
                      <Button asChild variant="outline" size="sm">
                        <Link href={routes.admin_office_resource(row.id)}>
                          Edit
                          <ArrowRight className="size-3.5" aria-hidden />
                        </Link>
                      </Button>
                    ) : null,
                },
              ]}
            />

            {resources.pagination.totalPages > 1 ? (
              <Pagination
                pagination={resources.pagination}
                onPageChange={(page) => visit({}, page)}
              />
            ) : null}
          </SurfaceCardContent>
        </SurfaceCard>
      </div>
    </PermissionRequired>
  );
}

OfficeResourcesAdministration.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Office Resources",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Office Resources" },
        ],
      },
      variant: "wide",
    },
  ] as const;
