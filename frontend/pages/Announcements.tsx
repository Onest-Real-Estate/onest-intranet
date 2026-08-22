import { Head, Link, router, usePage } from "@inertiajs/react";
import { Info, Newspaper } from "lucide-react";

import {
  EmptyState,
  FilterControls,
  FilterField,
  PageHeader,
  Pagination,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  activeFilterCount,
  categoryPresentation,
  priorityPresentation,
  rejectedFilterMessage,
} from "@/lib/announcements";
import { buildListUrl } from "@/lib/list-query";
import { routes } from "@/lib/routes";
import type {
  AnnouncementFilters,
  AnnouncementRow,
  AnnouncementsPageProps,
  FilterOption,
} from "@/types";

/** `Select` cannot hold an empty value, so "any" needs a sentinel of its own. */
const ANY = "__any__";

function formatPublished(value: string | null): string {
  if (!value) {
    return "Not yet published";
  }
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
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
    <FilterField label={label}>
      <Select
        value={value || ANY}
        onValueChange={(next) => onChange(next === ANY ? "" : next)}
      >
        <SelectTrigger aria-label={label}>
          <SelectValue placeholder="Any" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>Any</SelectItem>
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

function AnnouncementCard({ row }: { row: AnnouncementRow }) {
  const priority = priorityPresentation(row.priority);
  const category = categoryPresentation(row.category);

  return (
    <article aria-labelledby={`announcement-${row.id}-title`}>
      <SurfaceCard>
        <SurfaceCardContent className="grid gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={priority} />
            <StatusBadge status={category} />
            <span className="text-muted-foreground text-xs">
              {row.scope.label} · {row.scope.officeName}
            </span>
          </div>
          {/*
            The badges above are visual shorthand. This sentence is the same
            information in words, read by assistive technology and available to
            anyone the tones do not reach.
          */}
          <p className="sr-only">
            {row.priority.srLabel}. {row.category.srLabel}.
          </p>
          <h2
            id={`announcement-${row.id}-title`}
            className="text-lg leading-snug font-semibold text-balance"
          >
            <Link
              href={routes.announcement_detail(row.id)}
              className="hover:text-primary focus-visible:ring-ring rounded-sm focus-visible:ring-2 focus-visible:outline-none"
            >
              {row.title}
            </Link>
          </h2>
          {row.summary ? (
            <p className="text-muted-foreground text-sm leading-6">{row.summary}</p>
          ) : null}
          <p className="text-muted-foreground text-xs">
            Published {formatPublished(row.publishedAt)}
          </p>
        </SurfaceCardContent>
      </SurfaceCard>
    </article>
  );
}

/**
 * The brokerage news feed.
 *
 * Every row on this page already passed the server's audience and publication
 * filters; the page never asks for a wider set and holds no office identifier
 * it could ask with. Ordering is the server's too — priority first, then
 * recency — so the list arrives in its documented order and the client does
 * not re-sort it into a different one.
 */
export default function Announcements() {
  const { feed, filterOptions } = usePage<AnnouncementsPageProps>().props;
  const filters = feed.filters as AnnouncementFilters;
  const notice = rejectedFilterMessage(filters);

  function visit(next: Partial<AnnouncementFilters>, page?: number) {
    router.get(
      buildListUrl(routes.announcements(), window.location.search, {
        page,
        filters: { ...filters, ...next, rejected: undefined },
      }),
      {},
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  return (
    <>
      <Head title="Announcements" />
      <div className="grid gap-8">
        <PageHeader
          title="Announcements"
          description="Brokerage, region, and office news. Urgent notices sort first, then the most recent."
        />

        <FilterControls
          activeCount={activeFilterCount(filters)}
          onReset={() => visit({ category: "", priority: "" })}
        >
          <FilterSelect
            label="Category"
            value={filters.category}
            options={filterOptions.categories}
            onChange={(next) => visit({ category: next })}
          />
          <FilterSelect
            label="Priority"
            value={filters.priority}
            options={filterOptions.priorities}
            onChange={(next) => visit({ priority: next })}
          />
        </FilterControls>

        {notice ? (
          <p
            role="status"
            className="text-muted-foreground flex items-start gap-2 text-sm"
          >
            <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
            {notice}
          </p>
        ) : null}

        {feed.items.length === 0 ? (
          <SurfaceCard>
            <EmptyState
              icon={Newspaper}
              title={
                activeFilterCount(filters) > 0
                  ? "No announcements match these filters"
                  : "No announcements yet"
              }
              description={
                activeFilterCount(filters) > 0
                  ? "Reset the filters to see everything published to your offices."
                  : "News published to your office, region, or the brokerage will appear here."
              }
            />
          </SurfaceCard>
        ) : (
          <section aria-label="Announcements" className="grid gap-4">
            {feed.items.map((row) => (
              <AnnouncementCard key={row.id} row={row} />
            ))}
          </section>
        )}

        {feed.pagination.totalPages > 1 ? (
          <Pagination
            pagination={feed.pagination}
            onPageChange={(page) => visit({}, page)}
          />
        ) : null}
      </div>
    </>
  );
}

Announcements.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Announcements",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Announcements" },
        ],
      },
    },
  ] as const;
