import { Head, Link, router, usePage } from "@inertiajs/react";
import { BadgeCheck, CalendarClock, FileText, Pencil, Plus, Tag } from "lucide-react";
import { useState } from "react";
import {
  CreateSheet,
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
import {
  DocumentCreateFields,
  type DocumentDraftDefaults,
} from "@/components/documents/DocumentCreateFields";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Badge } from "@/components/ui/badge";
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
import type { DocumentsAdministrationPageProps, DocumentsAdminRow } from "@/types";

const MANAGE = { all: ["web.manage_documents"] };

const LIFECYCLE_OPTIONS = [
  { value: "draft", label: "Draft" },
  { value: "scheduled", label: "Scheduled" },
  { value: "live", label: "Live" },
  { value: "expired", label: "Expired" },
  { value: "superseded", label: "Superseded" },
  { value: "retired", label: "Retired" },
];

const AUDIENCE_OPTIONS = [
  { value: "company", label: "Everyone" },
  { value: "role", label: "By role" },
  { value: "region", label: "By region" },
  { value: "office", label: "By office" },
  { value: "user", label: "Named people" },
];

const FILTER_KEYS = [
  "lifecycle",
  "category",
  "audience",
  "author",
  "office",
  "publishedFrom",
  "publishedTo",
] as const;

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

function audienceLabel(row: DocumentsAdminRow): string {
  if (row.audience.length === 0) {
    return "No audience yet";
  }
  if (row.audience.length === 1) {
    return row.audience[0].label;
  }
  return `${row.audience[0].label} + ${row.audience.length - 1} more`;
}

function DocumentsAdministrationPage() {
  const {
    documents,
    filterOptions,
    createOptions,
    createSheet,
    capabilities,
    errors,
    csrfToken,
  } = usePage<DocumentsAdministrationPageProps>().props;
  const filters = documents.filters;
  const [query, setQuery] = useState(filters.q ?? "");
  const [createOpen, setCreateOpen] = useState(
    Boolean(createSheet?.open) || hasValidationErrors(errors),
  );
  const draft = (createSheet?.draft ?? {}) as DocumentDraftDefaults;

  function visit(patch: Partial<Record<FilterKey | "q", string>> & { page?: number }) {
    router.get(
      routes.admin_documents(),
      {
        q: query,
        lifecycle: filters.lifecycle,
        category: filters.category,
        audience: filters.audience,
        author: filters.author,
        office: filters.office,
        publishedFrom: filters.publishedFrom,
        publishedTo: filters.publishedTo,
        page: 1,
        ...patch,
      },
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  function reset() {
    setQuery("");
    router.get(
      routes.admin_documents(),
      {},
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  const activeCount = FILTER_KEYS.filter((key) => Boolean(filters[key])).length;

  return (
    <div className="grid gap-8">
      <Head title="Documents" />
      <PageHeader
        title="Documents"
        description="Draft, preview, schedule, publish, and retire brokerage forms. Saving a draft never reaches anybody — publishing is a separate, deliberate step."
        actions={
          capabilities.canAuthor ? (
            <Button type="button" onClick={() => setCreateOpen(true)}>
              <Plus className="size-4" aria-hidden />
              New document
            </Button>
          ) : null
        }
      />

      <FormErrorSummary errors={errors} />

      {capabilities.canAuthor ? (
        <CreateSheet
          open={createOpen}
          onOpenChange={setCreateOpen}
          title="New document"
          description="Save a draft and land in the workspace, where you can preview it, add files, and publish when it is ready."
          action={routes.document_admin_create()}
          csrfToken={csrfToken}
          formId="document-create-form"
          submitLabel="Save draft"
        >
          <DocumentCreateFields
            defaults={draft}
            offices={createOptions.offices}
            categories={createOptions.categories}
            audience={createOptions.audience}
          />
        </CreateSheet>
      ) : null}

      <SurfaceCard>
        <PanelHeader
          divided
          title="Versions in your scope"
          description="Most recently edited first."
          meta={
            <span className="text-muted-foreground text-xs font-medium tabular-nums">
              {documents.pagination.totalItems}{" "}
              {documents.pagination.totalItems === 1 ? "version" : "versions"}
            </span>
          }
        />
        <SurfaceCardContent className="grid gap-4">
          <FilterControls
            activeCount={activeCount}
            onReset={reset}
            leading={
              <SearchControl
                label="Search documents"
                value={query}
                onValueChange={setQuery}
                onSearch={(next) => visit({ q: next })}
                onClear={() => visit({ q: "" })}
                placeholder="Name, description, or family key"
              />
            }
          >
            <FilterField label="Lifecycle">
              <Select
                value={filters.lifecycle || "all"}
                onValueChange={(next) =>
                  visit({ lifecycle: next === "all" ? "" : next })
                }
              >
                <SelectTrigger aria-label="Filter by lifecycle">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Any state</SelectItem>
                  {LIFECYCLE_OPTIONS.map((option) => (
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

            <FilterField label="Audience">
              <Select
                value={filters.audience || "all"}
                onValueChange={(next) =>
                  visit({ audience: next === "all" ? "" : next })
                }
              >
                <SelectTrigger aria-label="Filter by audience">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Any audience</SelectItem>
                  {AUDIENCE_OPTIONS.map((option) => (
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

            <FilterField label="Author">
              <Input
                aria-label="Filter by author"
                defaultValue={filters.author}
                placeholder="Name or email"
                onBlur={(event) => {
                  if (event.target.value !== filters.author) {
                    visit({ author: event.target.value });
                  }
                }}
              />
            </FilterField>

            <FilterField label="Published from">
              <Input
                type="date"
                aria-label="Published on or after"
                defaultValue={filters.publishedFrom}
                onChange={(event) => visit({ publishedFrom: event.target.value })}
              />
            </FilterField>

            <FilterField label="Published until">
              <Input
                type="date"
                aria-label="Published on or before"
                defaultValue={filters.publishedTo}
                onChange={(event) => visit({ publishedTo: event.target.value })}
              />
            </FilterField>
          </FilterControls>

          <DataTable
            frame="bleed"
            caption="Document versions you may manage"
            rows={documents.items}
            rowKey={(row) => String(row.id)}
            emptyTitle="No documents match"
            emptyDescription="Nothing in your scope matches these filters. Clear them, or start a new draft."
            columns={[
              {
                id: "name",
                header: "Document",
                icon: FileText,
                cell: (row) => (
                  <div className="grid min-w-40 gap-0.5 sm:min-w-64">
                    <span className="truncate font-semibold">{row.name}</span>
                    <span className="text-muted-foreground truncate text-xs">
                      {row.key} · {row.ownerOffice.name} · {audienceLabel(row)}
                    </span>
                  </div>
                ),
              },
              {
                id: "lifecycle",
                header: "State",
                icon: BadgeCheck,
                cell: (row) => (
                  <div className="flex flex-wrap items-center gap-1.5">
                    <StatusBadge
                      status={{
                        label: row.lifecycle.label,
                        tone: toStatusTone(row.lifecycle.tone),
                      }}
                    />
                    {row.lifecycle.code === "scheduled" ? (
                      <span className="text-muted-foreground text-xs">
                        {formatDate(row.effectiveAt)}
                      </span>
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
                      <Link href={routes.document_admin_edit(row.id)}>
                        <span className="sr-only">Open {row.name}</span>
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

          {documents.pagination.totalPages > 1 ? (
            <Pagination
              pagination={documents.pagination}
              onPageChange={(page) => visit({ page })}
            />
          ) : null}
        </SurfaceCardContent>
      </SurfaceCard>

      {!capabilities.canPublish ? (
        <p className="text-muted-foreground flex items-start gap-2 text-sm">
          <FileText className="mt-0.5 size-4 shrink-0" aria-hidden />
          You can write and edit drafts. Publishing, scheduling, and superseding need
          the publication grant — ask whoever holds it in your office to take the last
          step.
        </p>
      ) : null}
    </div>
  );
}

export default function DocumentsAdministration() {
  return (
    <PermissionRequired permission={MANAGE}>
      <DocumentsAdministrationPage />
    </PermissionRequired>
  );
}

DocumentsAdministration.layout = () =>
  [
    HubLayout,
    {
      variant: "wide",
      context: {
        title: "Documents",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Documents", href: routes.admin_documents() },
        ],
      },
    },
  ] as const;
