import { Head, Link, router, usePage } from "@inertiajs/react";
import {
  BookOpen,
  CalendarClock,
  ChevronRight,
  GraduationCap,
  Info,
} from "lucide-react";

import {
  EmptyState,
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
import {
  activeFilterCount,
  completionPresentation,
  contentTypePresentation,
  formatDuration,
  rejectedFilterMessage,
} from "@/lib/training";
import type {
  FilterOption,
  TrainingFilters,
  TrainingLearningPageProps,
  TrainingRow,
} from "@/types";

const ANY = "__any__";

const VIEW_OPTIONS = [
  { value: "all", label: "All" },
  { value: "required", label: "Required" },
  { value: "recommended", label: "Recommended" },
] as const;

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
        <SelectTrigger size="sm" aria-label={label}>
          <SelectValue placeholder={`Any ${label.toLowerCase()}`} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>Any {label.toLowerCase()}</SelectItem>
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

function TrainingCard({ row }: { row: TrainingRow }) {
  const contentType = contentTypePresentation(row.contentType);
  const completion = completionPresentation(row.completion.status);
  const duration = formatDuration(row.estimatedMinutes);
  const titleId = `training-${row.id}-title`;

  return (
    <article aria-labelledby={titleId}>
      <SurfaceCard interactive className="group relative">
        <SurfaceCardContent className="flex min-w-0 items-start gap-4">
          <div className="grid min-w-0 flex-1 gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={contentType} />
              {row.isRequired ? (
                <StatusBadge status={{ label: "Required", tone: "warning" }} />
              ) : null}
              <StatusBadge status={completion} />
              {duration ? (
                <span className="text-muted-foreground text-xs">{duration}</span>
              ) : null}
              <span className="text-muted-foreground text-xs">
                {row.scope.label} · {row.scope.officeName}
              </span>
            </div>
            <p className="sr-only">
              {contentType.srLabel}.{" "}
              {row.isRequired ? "Required training." : "Optional training."}{" "}
              {completion.label}.
            </p>
            <h2
              id={titleId}
              className="text-base leading-snug font-semibold text-balance"
            >
              <Link
                href={routes.training_detail(row.id)}
                className="group-hover:text-primary focus-visible:ring-ring rounded-sm transition-colors duration-(--motion-fast) focus-visible:ring-2 focus-visible:outline-none"
              >
                <span className="absolute inset-0" aria-hidden />
                {row.title}
              </Link>
            </h2>
            {row.summary ? (
              <p className="text-muted-foreground line-clamp-2 text-sm leading-6">
                {row.summary}
              </p>
            ) : null}
            <div className="text-muted-foreground flex items-center gap-1.5 text-xs">
              <CalendarClock className="size-3.5 shrink-0" aria-hidden />
              Published{" "}
              {row.publishedAt
                ? new Date(row.publishedAt).toLocaleDateString()
                : "recently"}
            </div>
          </div>
          <ChevronRight
            aria-hidden
            className="text-muted-foreground/60 group-hover:text-foreground mt-2 hidden size-4 shrink-0 transition-colors duration-(--motion-fast) sm:block"
          />
        </SurfaceCardContent>
      </SurfaceCard>
    </article>
  );
}

export default function TrainingLearning() {
  const { library, filterOptions, requiredSummary } =
    usePage<TrainingLearningPageProps>().props;
  const filters = library.filters as TrainingFilters;
  const notice = rejectedFilterMessage(filters);
  const summary = requiredSummary ?? library.requiredSummary;

  function visit(next: Partial<TrainingFilters>, page?: number) {
    router.get(
      buildListUrl(routes.training_learning(), window.location.search, {
        page,
        filters: { ...filters, ...next, rejected: undefined },
      }),
      {},
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  return (
    <>
      <Head title="Training & learning" />
      <div className="grid gap-8">
        <PageHeader
          title="Training & learning"
          description="Required and recommended training for your role and office. Required items are listed first."
          meta={
            summary ? (
              <span className="text-muted-foreground text-sm tabular-nums">
                {summary.requiredCount === 0
                  ? "No required training assigned"
                  : `${summary.completedCount} of ${summary.requiredCount} required complete (${summary.percent}%)`}
              </span>
            ) : undefined
          }
        />

        <fieldset className="flex flex-wrap gap-2 border-0 p-0">
          <legend className="sr-only">Training views</legend>
          {VIEW_OPTIONS.map((option) => (
            <Button
              key={option.value}
              type="button"
              size="sm"
              variant={filters.view === option.value ? "default" : "outline"}
              aria-pressed={filters.view === option.value}
              onClick={() => visit({ view: option.value })}
            >
              {option.label}
            </Button>
          ))}
        </fieldset>

        <FilterControls
          activeCount={activeFilterCount(filters)}
          onReset={() =>
            visit({
              category: "",
              type: "",
              required: "",
              tool: "",
              completion: "",
              view: "all",
              q: "",
            })
          }
          leading={
            <SearchControl
              value={filters.q}
              onSearch={(next) => visit({ q: next })}
              label="Search training"
              placeholder="Search training"
            />
          }
        >
          <FilterSelect
            label="Category"
            value={filters.category}
            options={filterOptions.categories}
            onChange={(next) => visit({ category: next })}
          />
          <FilterSelect
            label="Type"
            value={filters.type}
            options={filterOptions.contentTypes}
            onChange={(next) => visit({ type: next })}
          />
          <FilterSelect
            label="Required"
            value={filters.required}
            options={[
              { value: "true", label: "Required only" },
              { value: "false", label: "Optional only" },
            ]}
            onChange={(next) => visit({ required: next })}
          />
          <FilterSelect
            label="Tool"
            value={filters.tool}
            options={filterOptions.tools}
            onChange={(next) => visit({ tool: next })}
          />
          <FilterSelect
            label="Completion"
            value={filters.completion}
            options={filterOptions.completions}
            onChange={(next) => visit({ completion: next })}
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

        {library.items.length === 0 ? (
          <SurfaceCard>
            <EmptyState
              icon={filters.view === "required" ? GraduationCap : BookOpen}
              title={
                activeFilterCount(filters) > 0
                  ? "No training matches these filters"
                  : filters.view === "required"
                    ? "No required training right now"
                    : filters.view === "recommended"
                      ? "No recommended training right now"
                      : "No training published yet"
              }
              description={
                activeFilterCount(filters) > 0
                  ? "Reset the filters to see everything available to you."
                  : "Training published to your role and office will appear here."
              }
            />
          </SurfaceCard>
        ) : (
          <section aria-label="Training library" className="grid gap-3">
            {library.items.map((row) => (
              <TrainingCard key={row.id} row={row} />
            ))}
          </section>
        )}

        {library.pagination.totalPages > 1 ? (
          <Pagination
            pagination={library.pagination}
            onPageChange={(page) => visit({}, page)}
          />
        ) : null}
      </div>
    </>
  );
}

TrainingLearning.layout = () =>
  [
    HubLayout,
    {
      variant: "wide",
      context: {
        title: "Training & learning",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Training & learning" },
        ],
      },
    },
  ] as const;
