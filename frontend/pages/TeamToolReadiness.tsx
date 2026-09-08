import { Head, Link, router, usePage } from "@inertiajs/react";
import { Check, Users } from "lucide-react";
import { useState } from "react";

import {
  EmptyState,
  PageHeader,
  PanelHeader,
  SearchControl,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import type { TeamToolReadinessPageProps } from "@/types";

const ACCESS = { all: ["web.view_new_agents"] };

/**
 * How far everybody this reader covers has got.
 *
 * Ordered least-ready first, deliberately: this page exists to find the people
 * who are still blocked, and a list sorted alphabetically makes somebody read
 * all forty rows to find the three that matter.
 *
 * The bar is a hairline under each name rather than a column of widgets. Forty
 * progress rings is a page about progress rings; forty ruled rows is a page
 * about people.
 */
export default function TeamToolReadiness() {
  const { agents, filters } = usePage<TeamToolReadinessPageProps>().props;
  // Seeded from the server so a reload keeps the term, but locally held while
  // typing — `SearchControl` is controlled when given `value`, and passing the
  // server's filter without an `onValueChange` would freeze the box empty.
  const [query, setQuery] = useState(filters.q);
  const outstanding = agents.filter((agent) => !agent.complete).length;

  function search(q: string) {
    setQuery(q);
    router.get(routes.team_tool_readiness(), q ? { q } : {}, {
      preserveState: true,
      preserveScroll: true,
      replace: true,
    });
  }

  return (
    <PermissionRequired permission={ACCESS}>
      <div className="grid gap-8">
        <Head title="Tool readiness" />
        <PageHeader
          title="Tool readiness"
          description="Which accounts and apps the agents you cover still need."
        />

        <SurfaceCard>
          <PanelHeader
            divided
            title="Agents"
            meta={
              <span className="text-muted-foreground text-xs tabular-nums">
                {outstanding > 0
                  ? `${outstanding} still setting up`
                  : `${agents.length} all set`}
              </span>
            }
          />
          <SurfaceCardContent className="grid gap-4 px-0">
            <div className="px-5">
              <SearchControl
                label="Search agents"
                value={query}
                onValueChange={setQuery}
                onSearch={search}
                onClear={() => search("")}
                placeholder="Name or email"
              />
            </div>
            {agents.length > 0 ? (
              <ul className="divide-border/70 divide-y">
                {agents.map((agent) => (
                  <li key={agent.id}>
                    <Link
                      href={routes.agent_tools(agent.id)}
                      className="hover:bg-accent/40 focus-visible:ring-ring grid gap-2 px-5 py-3.5 transition-colors focus-visible:ring-2 focus-visible:outline-none"
                    >
                      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                        <span className="text-sm font-medium">{agent.name}</span>
                        {agent.office ? (
                          <span className="text-muted-foreground truncate text-xs">
                            {agent.office}
                          </span>
                        ) : null}
                        <span
                          className={cn(
                            "ml-auto shrink-0 text-xs tabular-nums",
                            agent.complete
                              ? "text-success font-medium"
                              : "text-muted-foreground",
                          )}
                        >
                          {agent.complete ? (
                            <span className="inline-flex items-center gap-1">
                              <Check className="size-3.5" aria-hidden />
                              Ready
                            </span>
                          ) : (
                            `${agent.ready} of ${agent.total}`
                          )}
                        </span>
                      </div>
                      <div
                        className="bg-muted h-1 w-full overflow-hidden rounded-full"
                        role="progressbar"
                        aria-valuenow={agent.percent}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-label={`${agent.name}: ${agent.ready} of ${agent.total} tools ready`}
                      >
                        <div
                          className={cn(
                            "h-full rounded-full",
                            agent.complete ? "bg-success" : "bg-primary",
                          )}
                          style={{ width: `${agent.percent}%` }}
                        />
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="px-5">
                <EmptyState
                  icon={Users}
                  tone="muted"
                  title={filters.q ? "No agent matches that" : "Nobody to show"}
                  description={
                    filters.q
                      ? "Try a different name, or clear the search."
                      : "Agents in the offices you cover appear here once they have an account."
                  }
                />
              </div>
            )}
          </SurfaceCardContent>
        </SurfaceCard>
      </div>
    </PermissionRequired>
  );
}

TeamToolReadiness.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Tool readiness",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Tool readiness" },
        ],
      },
    },
  ] as const;
