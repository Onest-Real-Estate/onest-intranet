import { Head, Link, router, usePage } from "@inertiajs/react";
import {
  BadgeCheck,
  CalendarClock,
  Megaphone,
  Pencil,
  Pin,
  PinOff,
  Plus,
  Tag,
} from "lucide-react";
import { useState } from "react";
import {
  AnnouncementCreateFields,
  type AnnouncementDraftDefaults,
} from "@/components/announcements/AnnouncementCreateFields";
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
} from "@/components/design-system";
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
import { toFormData } from "@/lib/form-data";
import { routes } from "@/lib/routes";
import { hasValidationErrors } from "@/lib/validation";
import type {
  AnnouncementAdministrationPageProps,
  AnnouncementAdminRow,
} from "@/types";

const MANAGE = { all: ["web.manage_announcements"] };

const LIFECYCLE_OPTIONS = [
  { value: "draft", label: "Draft" },
  { value: "scheduled", label: "Scheduled" },
  { value: "live", label: "Live" },
  { value: "expired", label: "Expired" },
  { value: "archived", label: "Archived" },
];

const AUDIENCE_OPTIONS = [
  { value: "company", label: "Everyone" },
  { value: "role", label: "By role" },
  { value: "region", label: "By region" },
  { value: "office", label: "By office" },
  { value: "user", label: "Named people" },
];

/** Keys the filter bar owns. `q` has its own control, so it is counted apart. */
const FILTER_KEYS = [
  "lifecycle",
  "category",
  "priority",
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

function audienceLabel(row: AnnouncementAdminRow): string {
  if (row.audience.length === 0) {
    return "No audience yet";
  }
  if (row.audience.length === 1) {
    return row.audience[0].label;
  }
  return `${row.audience[0].label} + ${row.audience.length - 1} more`;
}

/**
 * The announcement work queue.
 *
 * Every row here already passed the server's scope filter, and `capabilities`
 * repeats the server's answer about the three grants so a control is never
 * offered for an action the save would refuse. The page cannot ask for a wider
 * set and could not receive one.
 */
function AnnouncementAdministrationPage() {
  const {
    announcements,
    filterOptions,
    createOptions,
    createSheet,
    capabilities,
    errors,
    csrfToken,
  } = usePage<AnnouncementAdministrationPageProps>().props;
  const filters = announcements.filters;
  const [query, setQuery] = useState(filters.q ?? "");
  // A rejected create comes back as this page with the drawer flagged open, so
  // the author fixes the field they were already looking at rather than
  // discovering the failure on a page they had left.
  const [createOpen, setCreateOpen] = useState(
    Boolean(createSheet?.open) || hasValidationErrors(errors),
  );
  const draft = (createSheet?.draft ?? {}) as AnnouncementDraftDefaults;

  function visit(patch: Partial<Record<FilterKey | "q", string>> & { page?: number }) {
    router.get(
      routes.admin_announcements(),
      {
        q: query,
        lifecycle: filters.lifecycle,
        category: filters.category,
        priority: filters.priority,
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
      routes.admin_announcements(),
      {},
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  function togglePin(row: AnnouncementAdminRow) {
    router.post(
      routes.announcement_pin(row.id),
      // The version token travels with the action, so pinning a row somebody
      // else has just archived is refused rather than silently applied.
      toFormData({
        pinned: row.isPinned ? "" : "on",
        expected_version: row.version,
      }),
      { preserveScroll: true },
    );
  }

  const activeCount = FILTER_KEYS.filter((key) => Boolean(filters[key])).length;

  return (
    <div className="grid gap-8">
      <Head title="Announcements" />
      <PageHeader
        title="Announcements"
        description="Draft, preview, schedule, and retire the notices your offices send. Saving a draft never reaches anybody — publishing is a separate, deliberate step."
        actions={
          capabilities.canAuthor ? (
            <Button type="button" onClick={() => setCreateOpen(true)}>
              <Plus className="size-4" aria-hidden />
              New announcement
            </Button>
          ) : null
        }
      />

      <FormErrorSummary errors={errors} />

      {capabilities.canAuthor ? (
        <CreateSheet
          open={createOpen}
          onOpenChange={setCreateOpen}
          title="New announcement"
          description="Save a draft and land in the workspace, where you can preview it, add a hero image, and publish when it is ready."
          action={routes.announcement_create()}
          csrfToken={csrfToken}
          formId="announcement-create-form"
          submitLabel="Save draft"
        >
          <AnnouncementCreateFields
            defaults={draft}
            offices={createOptions.offices}
            categories={createOptions.categories}
            priorities={createOptions.priorities}
            audience={createOptions.audience}
          />
        </CreateSheet>
      ) : null}

      <SurfaceCard>
        <PanelHeader
          divided
          title="Announcements in your scope"
          description="Most recently edited first."
          meta={
            <span className="text-muted-foreground text-xs font-medium tabular-nums">
              {announcements.pagination.totalItems}{" "}
              {announcements.pagination.totalItems === 1
                ? "announcement"
                : "announcements"}
            </span>
          }
        />
        <SurfaceCardContent className="grid gap-4">
          <FilterControls
            activeCount={activeCount}
            onReset={reset}
            leading={
              <SearchControl
                label="Search announcements"
                value={query}
                onValueChange={setQuery}
                onSearch={(next) => visit({ q: next })}
                onClear={() => visit({ q: "" })}
                placeholder="Title, summary, or slug"
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

            <FilterField label="Priority">
              <Select
                value={filters.priority || "all"}
                onValueChange={(next) =>
                  visit({ priority: next === "all" ? "" : next })
                }
              >
                <SelectTrigger aria-label="Filter by priority">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Any priority</SelectItem>
                  {filterOptions.priorities.map((option) => (
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
            caption="Announcements you may manage"
            rows={announcements.items}
            rowKey={(row) => String(row.id)}
            emptyTitle="No announcements match"
            emptyDescription="Nothing in your scope matches these filters. Clear them, or start a new draft."
            columns={[
              {
                id: "title",
                header: "Announcement",
                icon: Megaphone,
                cell: (row) => (
                  <div className="grid min-w-40 gap-0.5 sm:min-w-64">
                    <span className="flex items-center gap-1.5 font-semibold">
                      {row.isPinned ? (
                        <Pin
                          className="text-muted-foreground size-3.5 shrink-0"
                          aria-label="Pinned"
                        />
                      ) : null}
                      <span className="truncate">{row.title}</span>
                    </span>
                    <span className="text-muted-foreground truncate text-xs">
                      {row.ownerOffice.name} · {audienceLabel(row)}
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
                        tone: row.lifecycle.tone,
                      }}
                    />
                    {row.lifecycle.code === "scheduled" ? (
                      <span className="text-muted-foreground text-xs">
                        {formatDate(row.publishAt)}
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
                    <Badge variant="outline">{row.category.label}</Badge>
                    <Badge variant="outline">{row.priority.label}</Badge>
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
                    {capabilities.canPin && row.status === "published" ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => togglePin(row)}
                      >
                        {row.isPinned ? (
                          <PinOff className="size-3.5" aria-hidden />
                        ) : (
                          <Pin className="size-3.5" aria-hidden />
                        )}
                        <span className="sr-only">
                          {row.isPinned ? "Unpin" : "Pin"} {row.title}
                        </span>
                      </Button>
                    ) : null}
                    <Button
                      variant="outline"
                      size="sm"
                      asChild
                      className="size-8 px-0 sm:h-8 sm:w-auto sm:px-3"
                    >
                      <Link href={routes.announcement_edit(row.id)}>
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

          {announcements.pagination.totalPages > 1 ? (
            <Pagination
              pagination={announcements.pagination}
              onPageChange={(page) => visit({ page })}
            />
          ) : null}
        </SurfaceCardContent>
      </SurfaceCard>

      {!capabilities.canPublish ? (
        <p className="text-muted-foreground flex items-start gap-2 text-sm">
          <Megaphone className="mt-0.5 size-4 shrink-0" aria-hidden />
          You can write and edit drafts. Publishing, scheduling, and archiving need the
          publication grant — ask whoever holds it in your office to take the last step.
        </p>
      ) : null}
    </div>
  );
}

export default function AnnouncementAdministration() {
  return (
    <PermissionRequired permission={MANAGE}>
      <AnnouncementAdministrationPage />
    </PermissionRequired>
  );
}

AnnouncementAdministration.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Announcements",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Announcements", href: routes.admin_announcements() },
        ],
      },
      variant: "standard",
    },
  ] as const;
