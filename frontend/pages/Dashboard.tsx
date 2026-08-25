import { Head, router, usePage } from "@inertiajs/react";
import { useMemo, useState } from "react";

import { DashboardGreeting } from "@/components/dashboard/DashboardGreeting";
import { DashboardProfileSwitcher } from "@/components/dashboard/DashboardProfileSwitcher";
import { DashboardScopeSelector } from "@/components/dashboard/DashboardScopeSelector";
import { DashboardWidgetSlot } from "@/components/dashboard/DashboardWidgetSlot";
import { HubLayout } from "@/components/HubLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuthorizationStaleness } from "@/hooks/use-authorization-staleness";
import { PREVIEW_SCOPE_OPTIONS } from "@/lib/dashboard/preview";
import {
  readRememberedProfile,
  rememberProfile,
  resolveDashboard,
  resolveWidgets,
} from "@/lib/dashboard/resolve";
import type { DashboardWidgetColumn } from "@/lib/dashboard/widget-registry";
import { routes } from "@/lib/routes";
import type { DashboardPageProps, MetricScopeLevel } from "@/types";

/**
 * Twelfths a `wide` widget may claim, spelled out because Tailwind needs to see
 * the class to emit it. Anything unlisted takes the full band.
 */
const SPAN_CLASS: Record<number, string> = {
  4: "h-full xl:col-span-4",
  5: "h-full xl:col-span-5",
  6: "h-full xl:col-span-6",
  7: "h-full xl:col-span-7",
  8: "h-full xl:col-span-8",
};

function spanClass(span: number | undefined): string {
  return (span && SPAN_CLASS[span]) || "h-full xl:col-span-12";
}

/**
 * One dashboard, eleven presentations.
 *
 * Which widgets appear and in what order is resolved from the reader's
 * effective roles and permissions in `lib/dashboard` — there is no per-role
 * page component and no role conditional below. Resolution decides layout
 * only: every widget is permission-filtered, and every provider behind it
 * re-applies the same permissions and the reader's scope server-side.
 */
export default function Dashboard() {
  const page = usePage<DashboardPageProps>().props;
  const { user, greeting, shell, assignment, scope } = page;

  // Null means "no remembered choice"; the reader's assigned profile wins.
  const [chosenProfileId, setChosenProfileId] = useState<string | null>(() =>
    readRememberedProfile(),
  );
  const { stale, acknowledge } = useAuthorizationStaleness(shell?.authorizationVersion);

  const resolved = useMemo(
    () => resolveDashboard(user, assignment, chosenProfileId),
    [user, assignment, chosenProfileId],
  );

  // The scope the server says these figures cover. Absent until the scope
  // payload ships, and never inferred client-side: guessing a breadth would
  // relabel an office figure as a company one.
  const serverScope = scope ?? null;
  const scopeLevel: MetricScopeLevel | null = serverScope
    ? (serverScope.options.find((option) => option.key === serverScope.selectedKey)
        ?.level ?? null)
    : null;

  const widgets = useMemo(
    () => resolveWidgets(resolved.profile, user, scopeLevel),
    [resolved.profile, user, scopeLevel],
  );

  const scopeOptions = serverScope ? serverScope.options : PREVIEW_SCOPE_OPTIONS;
  const showsScopeControl = scopeOptions.length > 0;
  const showsProfileControl = resolved.available.length > 1;
  const [previewScopeKey, setPreviewScopeKey] = useState(
    PREVIEW_SCOPE_OPTIONS[0]?.key ?? null,
  );

  if (!user) {
    return null;
  }

  function selectProfile(id: string) {
    // Returning to the assigned profile clears the memory rather than pinning
    // it, so a later reassignment is not silently overridden.
    const next = id === resolved.assigned.id ? null : id;
    rememberProfile(next);
    setChosenProfileId(next);
  }

  function refreshAll() {
    router.reload({ onSuccess: acknowledge });
  }

  const column = (name: DashboardWidgetColumn) =>
    widgets.filter((widget) => widget.definition.column === name);

  // Said once, at the top, rather than under every badge below.
  const hasPreview = widgets.some(
    (widget) => !widget.withheld && !widget.definition.backed,
  );

  const wide = column("wide");
  const main = column("main");
  const rail = column("rail");

  return (
    <div className="flex flex-1 flex-col gap-10">
      <Head title="Dashboard" />

      {/* Orientation is one compact band: identity and controls first, then
          only the qualifiers that affect the figures below. */}
      <div className="grid gap-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <DashboardGreeting greeting={greeting} user={user} />
          {showsScopeControl || showsProfileControl ? (
            <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center lg:shrink-0">
              <DashboardScopeSelector
                options={scopeOptions}
                selectedKey={serverScope ? serverScope.selectedKey : previewScopeKey}
                reloadProps={widgets.map((widget) => widget.definition.prop)}
                interactive={serverScope !== null}
                onSelect={serverScope ? undefined : setPreviewScopeKey}
              />
              <DashboardProfileSwitcher
                profiles={resolved.available}
                activeId={resolved.profile.id}
                onSelect={selectProfile}
              />
            </div>
          ) : null}
        </div>

        {hasPreview || stale ? (
          <div className="grid gap-3">
            {hasPreview ? (
              <p className="text-muted-foreground flex items-start gap-2 text-sm leading-5">
                <Badge variant="warning" className="mt-0.5 shrink-0">
                  Preview data
                </Badge>
                <span>
                  Panels marked this way show illustrative figures while their data
                  sources are being connected.
                </span>
              </p>
            ) : null}

            {/* One announcement for a page-wide condition. Individual panels carry
                a quiet stale mark; the action to fix it lives here, once. */}
            {stale ? (
              <div
                role="status"
                className="border-warning/30 bg-warning/10 text-warning-ink flex flex-wrap items-center gap-3 rounded-lg border px-4 py-3 text-sm"
              >
                <span>
                  Your roles or scope changed while this page was open. Refresh to see
                  the dashboard you are entitled to now.
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  className="ms-auto"
                  onClick={refreshAll}
                >
                  Refresh
                </Button>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      {/* Band: where things stand, and the tools to act on them. Figures and
          launchers are one thought, so they sit a section apart (24px) rather
          than a page apart. */}
      {wide.length > 0 ? (
        <div className="grid items-stretch gap-6 xl:grid-cols-12">
          {wide.map((widget) => (
            <div
              key={widget.definition.id}
              className={spanClass(widget.definition.span)}
            >
              <DashboardWidgetSlot resolved={widget} page={page} stale={stale} />
            </div>
          ))}
        </div>
      ) : null}

      {/* Band: the role-defining workflow leads in both DOM and visual order.
          Supporting daily and utility panels follow, so keyboard, screen-reader,
          mobile, and desktop reading order never disagree. */}
      <div className="grid items-start gap-6 xl:grid-cols-12">
        {main.length > 0 ? (
          <div
            data-dashboard-column="main"
            className={
              rail.length > 0
                ? "grid content-start gap-6 xl:col-span-8"
                : "grid content-start gap-6 xl:col-span-12"
            }
          >
            {main.map((widget) => (
              <DashboardWidgetSlot
                key={widget.definition.id}
                resolved={widget}
                page={page}
                stale={stale}
              />
            ))}
          </div>
        ) : null}
        {rail.length > 0 ? (
          <div
            data-dashboard-column="rail"
            className={
              main.length > 0
                ? "grid content-start gap-6 xl:col-span-4"
                : "grid content-start gap-6 xl:col-span-12"
            }
          >
            {rail.map((widget) => (
              <DashboardWidgetSlot
                key={widget.definition.id}
                resolved={widget}
                page={page}
                stale={stale}
              />
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

Dashboard.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Dashboard",
        breadcrumbs: [{ label: "Dashboard", href: routes.dashboard() }],
      },
      variant: "wide",
    },
  ] as const;
