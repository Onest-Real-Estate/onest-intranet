import { Head, Link, router, usePage } from "@inertiajs/react";
import {
  BadgeCheck,
  CalendarClock,
  ClipboardList,
  Pencil,
  Plus,
  ShieldCheck,
  Tag,
} from "lucide-react";
import { useState } from "react";

import {
  DataTable,
  FilterControls,
  FilterField,
  FormErrorSummary,
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
import { routes } from "@/lib/routes";
import type { ComplianceAdministrationPageProps, ComplianceAdminRow } from "@/types";

const MANAGE = { all: ["web.manage_policies"] };

const FILTER_KEYS = ["status", "category", "office"] as const;

type FilterKey = (typeof FILTER_KEYS)[number];

function formatDate(value: string | null): string {
  if (!value) {
    return "—";
  }
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
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

function ComplianceAdministrationPage() {
  const { policies, filterOptions, capabilities, errors } =
    usePage<ComplianceAdministrationPageProps>().props;
  const filters = policies.filters;
  const [query, setQuery] = useState(filters.q ?? "");

  function visit(patch: Partial<Record<FilterKey | "q", string>> & { page?: number }) {
    router.get(
      routes.admin_compliance(),
      {
        q: query,
        status: filters.status,
        category: filters.category,
        office: filters.office,
        page: 1,
        ...patch,
      },
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  function reset() {
    setQuery("");
    router.get(
      routes.admin_compliance(),
      {},
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  const activeCount = FILTER_KEYS.filter((key) => Boolean(filters[key])).length;

  return (
    <div className="grid gap-8">
      <Head title="Compliance administration" />
      <PageHeader
        title="Compliance administration"
        description="Draft, review, publish, and retire policies. Saving a draft never reaches anybody — publishing is a separate, deliberate step."
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

      <SurfaceCard>
        <PanelHeader
          divided
          title="Policies in your scope"
          description="Most recently edited first."
          meta={
            <span className="text-muted-foreground text-xs font-medium tabular-nums">
              {policies.pagination.totalItems}{" "}
              {policies.pagination.totalItems === 1 ? "policy" : "policies"}
            </span>
          }
        />
        <SurfaceCardContent className="grid gap-4">
          <FilterControls
            activeCount={activeCount}
            onReset={reset}
            leading={
              <SearchControl
                label="Search policies"
                value={query}
                onValueChange={setQuery}
                onSearch={(next) => visit({ q: next })}
                onClear={() => visit({ q: "" })}
                placeholder="Title or summary"
              />
            }
          >
            <FilterField label="Status">
              <Select
                value={filters.status || "all"}
                onValueChange={(next) => visit({ status: next === "all" ? "" : next })}
              >
                <SelectTrigger aria-label="Filter by status">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Any status</SelectItem>
                  {filterOptions.statuses.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FilterField>

            <FilterField label="Category">
              <Select
                value={filters.category || "all"}
                onValueChange={(next) =>
                  visit({ category: next === "all" ? "" : next })
                }
              >
                <SelectTrigger aria-label="Filter by category">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Any category</SelectItem>
                  {filterOptions.categories.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FilterField>

            <FilterField label="Owning office">
              <Select
                value={filters.office || "all"}
                onValueChange={(next) => visit({ office: next === "all" ? "" : next })}
              >
                <SelectTrigger aria-label="Filter by owning office">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Any office</SelectItem>
                  {filterOptions.offices.map((option) => (
                    <SelectItem key={option.value} value={String(option.value)}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FilterField>
          </FilterControls>

          <DataTable
            frame="bleed"
            caption="Policies you may manage"
            rows={policies.items}
            rowKey={(row) => String(row.id)}
            emptyTitle="No policies match"
            emptyDescription="Nothing in your scope matches these filters. Clear them, or start a new draft."
            columns={[
              {
                id: "title",
                header: "Policy",
                icon: ShieldCheck,
                cell: (row) => (
                  <div className="grid min-w-40 gap-0.5 sm:min-w-64">
                    <span className="truncate font-semibold">{row.title}</span>
                    <span className="text-muted-foreground truncate text-xs">
                      {row.ownerOffice.name} · {audienceLabel(row)}
                    </span>
                  </div>
                ),
              },
              {
                id: "status",
                header: "Status",
                icon: BadgeCheck,
                cell: (row) => (
                  <div className="flex flex-wrap items-center gap-1.5">
                    <StatusBadge
                      status={{
                        label: row.status.label,
                        tone: toStatusTone(row.status.tone),
                      }}
                    />
                    {row.isMandatory ? (
                      <Badge variant="outline">Mandatory</Badge>
                    ) : null}
                  </div>
                ),
              },
              {
                id: "classification",
                header: "Classification",
                icon: Tag,
                cell: (row) => (
                  <div className="flex flex-wrap items-center gap-1.5">
                    {row.category ? (
                      <Badge variant="outline">{row.category.label}</Badge>
                    ) : (
                      <span className="text-muted-foreground text-xs">No category</span>
                    )}
                    <span className="text-muted-foreground text-xs">
                      {row.versionLabel}
                    </span>
                  </div>
                ),
                hideBelow: "4xl",
              },
              {
                id: "updated",
                header: "Last edited",
                icon: CalendarClock,
                cell: (row) => (
                  <div className="grid gap-0.5">
                    <span className="text-sm tabular-nums">
                      {formatDate(row.updatedAt)}
                    </span>
                    <span className="text-muted-foreground truncate text-xs">
                      {row.updatedBy || "—"}
                    </span>
                  </div>
                ),
                hideBelow: "5xl",
              },
              {
                id: "actions",
                header: <span className="sr-only">Actions</span>,
                cell: (row) => (
                  <div className="flex items-center justify-end gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      asChild
                      className="size-8 px-0 sm:h-8 sm:w-auto sm:px-3"
                    >
                      <Link href={routes.policy_admin_edit(row.id)}>
                        <span className="sr-only">Open {row.title}</span>
                        <span className="hidden sm:inline" aria-hidden>
                          Open
                        </span>
                        <Pencil className="size-3.5" aria-hidden />
                      </Link>
                    </Button>
                  </div>
                ),
                className: "text-right",
                headerClassName: "text-right",
              },
            ]}
          />

          {policies.pagination.totalPages > 1 ? (
            <Pagination
              pagination={policies.pagination}
              onPageChange={(page) => visit({ page })}
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
        title: "Compliance administration",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Compliance administration" },
        ],
      },
      variant: "standard",
    },
  ] as const;
