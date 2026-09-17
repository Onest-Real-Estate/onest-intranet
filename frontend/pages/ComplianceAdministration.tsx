import { Head, Link, router, usePage } from "@inertiajs/react";
import { ClipboardList, Plus, ShieldCheck } from "lucide-react";
import { useState } from "react";

import {
  DataTable,
  type DataTableColumn,
  FilterControls,
  FilterField,
  FormErrorSummary,
  MetricCard,
  MetricStrip,
  PageHeader,
  Pagination,
  PanelHeader,
  SearchControl,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
  toStatusTone,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Badge } from "@/components/ui/badge";
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
import type {
  ComplianceAdministrationPageProps,
  ComplianceAdminRow,
  FilterOption,
} from "@/types";

const MANAGE = { all: ["web.manage_policies"] };
const ANY = "__any__";

function formatDay(value: string | null): string {
  if (!value) {
    return "—";
  }
  return new Date(value).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

function audienceLabel(row: ComplianceAdminRow): string {
  if (row.audience.length === 0) {
    return "No audience yet";
  }
  if (row.audience.length === 1) {
    return row.audience[0].label;
  }
  return `${row.audience[0].label} + ${row.audience.length - 1} more`;
}

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
        value={value || ANY}
        onValueChange={(next) => onChange(next === ANY ? "" : next)}
      >
        <SelectTrigger size="sm" aria-label={label} className="w-full sm:w-44">
          <SelectValue placeholder={`Any ${label.toLowerCase()}`} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>Any {label.toLowerCase()}</SelectItem>
          {options.map((option) => (
            <SelectItem key={option.value} value={String(option.value)}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </FilterField>
  );
}

function ComplianceAdministrationPage() {
  const { policies, filterOptions, summary, capabilities, errors } =
    usePage<ComplianceAdministrationPageProps>().props;
  const filters = policies.filters;
  const [query, setQuery] = useState(filters.q ?? "");

  function visit(next: Partial<typeof filters>, page?: number) {
    router.get(
      buildListUrl(routes.admin_compliance(), window.location.search, {
        page,
        filters: { ...filters, q: query, ...next },
      }),
      {},
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  const activeCount = [filters.status, filters.category, filters.office].filter(
    Boolean,
  ).length;

  const columns: DataTableColumn<ComplianceAdminRow>[] = [
    {
      id: "title",
      header: "Policy",
      cell: (row) => (
        <span className="grid min-w-0 gap-0.5">
          <Link
            href={routes.policy_admin_edit(row.id)}
            className="hover:text-primary focus-visible:ring-ring truncate rounded-sm font-medium focus-visible:ring-2 focus-visible:outline-none"
          >
            {row.title}
          </Link>
          <span className="text-muted-foreground truncate text-xs">
            {row.ownerOffice.name} · {audienceLabel(row)}
          </span>
        </span>
      ),
    },
    {
      id: "status",
      header: "Status",
      cell: (row) => (
        <div className="flex flex-wrap items-center gap-1.5">
          <StatusBadge
            status={{
              label: row.status.label,
              tone: toStatusTone(row.status.tone),
            }}
          />
          {row.isMandatory ? <Badge variant="outline">Mandatory</Badge> : null}
        </div>
      ),
    },
    {
      id: "classification",
      header: "Classification",
      cell: (row) => (
        <span className="grid min-w-0 gap-0.5">
          <span className="truncate text-sm">
            {row.category?.label ?? "No category"}
          </span>
          <span className="text-muted-foreground text-xs">{row.versionLabel}</span>
        </span>
      ),
      hideBelow: "3xl",
    },
    {
      id: "updated",
      header: "Edited",
      cell: (row) => (
        <span className="grid min-w-0 gap-0.5">
          <span className="text-muted-foreground text-xs tabular-nums">
            {formatDay(row.updatedAt)}
          </span>
          <span className="text-muted-foreground truncate text-xs">
            {row.updatedBy || "—"}
          </span>
        </span>
      ),
      hideBelow: "5xl",
    },
  ];

  return (
    <div className="grid gap-8">
      <Head title="Compliance" />
      <PageHeader
        title="Compliance"
        description="Policies in the offices you cover."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" asChild>
              <Link href={routes.policy_ack_report()}>
                <ClipboardList className="size-4" aria-hidden />
                Acknowledgements
              </Link>
            </Button>
            {capabilities.canAuthor ? (
              <Button asChild>
                <Link href={routes.policy_admin_new()}>
                  <Plus className="size-4" aria-hidden />
                  New policy
                </Link>
              </Button>
            ) : null}
          </div>
        }
      />

      <FormErrorSummary errors={errors} />

      <MetricStrip>
        <MetricCard label="Draft" value={summary.draft} />
        <MetricCard label="In review" value={summary.inReview} />
        <MetricCard label="Published" value={summary.published} />
      </MetricStrip>

      <SurfaceCard>
        <PanelHeader divided title="Policies" />
        <SurfaceCardContent className="grid gap-4">
          <FilterControls
            activeCount={activeCount}
            onReset={() => {
              setQuery("");
              visit({ q: "", status: "", category: "", office: "" }, 1);
            }}
            leading={
              <SearchControl
                label="Search policies"
                value={query}
                onValueChange={setQuery}
                onSearch={(q) => visit({ q }, 1)}
                onClear={() => {
                  setQuery("");
                  visit({ q: "" }, 1);
                }}
                placeholder="Title or summary"
              />
            }
          >
            <FilterSelect
              label="Status"
              value={filters.status}
              options={filterOptions.statuses}
              onChange={(status) => visit({ status }, 1)}
            />
            <FilterSelect
              label="Category"
              value={filters.category}
              options={filterOptions.categories}
              onChange={(category) => visit({ category }, 1)}
            />
            <FilterSelect
              label="Office"
              value={filters.office}
              options={filterOptions.offices.map((option) => ({
                value: String(option.value),
                label: option.label,
              }))}
              onChange={(office) => visit({ office }, 1)}
            />
          </FilterControls>

          <DataTable
            frame="bleed"
            caption="Policies in your scope"
            rows={policies.items}
            rowKey={(row) => String(row.id)}
            getRowLabel={(row) => row.title}
            emptyTitle={
              activeCount > 0 ? "No policies match these filters" : "No policies yet"
            }
            emptyDescription={
              activeCount > 0
                ? "Reset the filters to see everything in your scope."
                : "Draft a policy and publish it when it is ready."
            }
            columns={columns}
          />

          {policies.pagination.totalPages > 1 ? (
            <Pagination
              pagination={policies.pagination}
              onPageChange={(page) => visit({}, page)}
            />
          ) : null}
        </SurfaceCardContent>
      </SurfaceCard>

      {!capabilities.canPublish ? (
        <p className="text-muted-foreground flex items-start gap-2 text-sm">
          <ShieldCheck className="mt-0.5 size-4 shrink-0" aria-hidden />
          You can write and edit drafts. Publishing and retiring need the publication
          grant — ask whoever holds it in your office to take the last step.
        </p>
      ) : null}
    </div>
  );
}

export default function ComplianceAdministration() {
  return (
    <PermissionRequired permission={MANAGE}>
      <ComplianceAdministrationPage />
    </PermissionRequired>
  );
}

ComplianceAdministration.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Compliance",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Compliance" },
        ],
      },
      variant: "wide",
    },
  ] as const;
