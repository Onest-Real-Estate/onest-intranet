import { Head, Link, usePage } from "@inertiajs/react";
import { Search as SearchIcon, TriangleAlert } from "lucide-react";

import {
  EmptyState,
  PageHeader,
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { routes } from "@/lib/routes";
import type { SearchPageProps } from "@/types";

/**
 * Full search results — a real, linkable destination.
 *
 * Served by the same aggregator as the header dialog, so the popover and this
 * page can never disagree about what the reader may see. Every hit was
 * authorized by its own domain before serialization, and every link is still a
 * door with its own lock: following one re-runs that destination's policy.
 */
export default function Search() {
  const { results } = usePage<SearchPageProps>().props;
  const hasHits = results.groups.some((group) => group.hits.length > 0);

  return (
    <div className="grid gap-8">
      <Head title={results.query ? `Search: ${results.query}` : "Search"} />
      <PageHeader
        title="Search"
        description={
          results.query
            ? `${results.total} result${results.total === 1 ? "" : "s"} for “${results.query}”`
            : "Search people, announcements, resources, and offices."
        }
      />

      {results.partial ? (
        <p className="text-warning-ink flex items-start gap-2 text-sm">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          Some sources did not answer, so these results are incomplete. Try again in a
          moment.
        </p>
      ) : null}

      {results.tooShort ? (
        <EmptyState
          icon={SearchIcon}
          title="Keep typing"
          description={`Search needs at least ${results.minLength} characters.`}
        />
      ) : !results.query ? (
        <EmptyState
          icon={SearchIcon}
          title="Nothing searched yet"
          description="Use the search box in the header, or press ⌘K."
        />
      ) : !hasHits ? (
        <EmptyState
          icon={SearchIcon}
          title="No results"
          description={`Nothing you can access matches “${results.query}”.`}
        />
      ) : (
        <div className="grid gap-6">
          {results.groups.map((group) => (
            <SurfaceCard key={group.key}>
              <PanelHeader
                divided
                title={group.label}
                meta={
                  <span className="text-muted-foreground text-xs font-medium tabular-nums">
                    {group.hits.length}
                    {group.truncated ? "+" : ""}
                  </span>
                }
              />
              <SurfaceCardContent>
                {group.failed ? (
                  <p className="text-muted-foreground text-sm">
                    This source did not answer. Its results are missing, not empty.
                  </p>
                ) : (
                  <ul className="grid gap-1">
                    {group.hits.map((hit) => (
                      <li key={`${group.key}-${hit.id}`}>
                        <Link
                          href={hit.href}
                          className="hover:bg-muted focus-visible:ring-ring grid gap-0.5 rounded-lg px-3 py-2.5 focus-visible:ring-2 focus-visible:outline-none"
                        >
                          <span className="text-sm font-semibold">{hit.title}</span>
                          {hit.snippet ? (
                            <span className="text-muted-foreground line-clamp-2 text-xs leading-5">
                              {hit.snippet}
                            </span>
                          ) : null}
                          {hit.meta ? (
                            <span className="text-muted-foreground text-xs">
                              {hit.meta}
                            </span>
                          ) : null}
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </SurfaceCardContent>
            </SurfaceCard>
          ))}
        </div>
      )}
    </div>
  );
}

Search.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Search",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Search", href: routes.search() },
        ],
      },
      variant: "standard",
    },
  ] as const;
