import { Head, router, usePage } from "@inertiajs/react";
import { useMemo, useState } from "react";

import { DashboardGreeting } from "@/components/dashboard/DashboardGreeting";
import { DashboardProfileSwitcher } from "@/components/dashboard/DashboardProfileSwitcher";
import { DashboardScopeSelector } from "@/components/dashboard/DashboardScopeSelector";
import { DashboardWidgetSlot } from "@/components/dashboard/DashboardWidgetSlot";
import { PendingModules } from "@/components/dashboard/PendingModules";
import { HubLayout } from "@/components/HubLayout";
import { Button } from "@/components/ui/button";
import { useAuthorizationStaleness } from "@/hooks/use-authorization-staleness";
import {
  naturalSpan,
  packRows,
  partitionPending,
  spanClass,
} from "@/lib/dashboard/layout";
import {
  readRememberedProfile,
  rememberProfile,
  resolveDashboard,
  resolveWidgets,
} from "@/lib/dashboard/resolve";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import type { DashboardPageProps, MetricScopeLevel } from "@/types";

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

  // Modules with nothing behind them leave the grid and are stated once at the
  // foot of the page. What is left is every panel that has — or is still
  // fetching — something to show.
  const { laidOut, pending } = useMemo(
    () => partitionPending(widgets, page),
    [widgets, page],
  );

  // Reading order is the profile's; only the widths are computed, so that every
  // row of the grid closes on the twelfth column and the page never ends in a
  // half-empty band.
  const placed = useMemo(
    () => packRows(laidOut, (widget) => naturalSpan(widget.definition)),
    [laidOut],
  );

  // No server scope means the reader has one breadth and nothing to choose;
  // the control is absent rather than offering breadths that do not apply.
  const scopeOptions = serverScope ? serverScope.options : [];
  const showsScopeControl = scopeOptions.length > 0;
  const showsProfileControl = resolved.available.length > 1;

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

  return (
    <div className="flex flex-1 flex-col gap-8">
      <Head title="Dashboard" />

      {/* Orientation is one masthead: identity, the qualifiers that affect
          every figure below, and a rule closing the block. The controls ride
          inside the header rather than beside it, so the rule spans the page
          and the title has something to sit on. */}
      <div className="grid gap-4">
        <DashboardGreeting
          greeting={greeting}
          user={user}
          actions={
            showsScopeControl || showsProfileControl ? (
              <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center">
                <DashboardScopeSelector
                  options={scopeOptions}
                  selectedKey={serverScope ? serverScope.selectedKey : null}
                  reloadProps={widgets.map((widget) => widget.definition.prop)}
                />
                <DashboardProfileSwitcher
                  profiles={resolved.available}
                  activeId={resolved.profile.id}
                  onSelect={selectProfile}
                />
              </div>
            ) : null
          }
        />

        {/* One announcement for a page-wide condition. Individual panels carry
            a quiet stale mark; the action to fix it lives here, once. */}
        {stale ? (
          <div
            role="status"
            className="border-chip-warning-edge bg-chip-warning text-warning-ink flex flex-wrap items-center gap-3 rounded-lg border px-4 py-3 text-sm"
          >
            <span>
              Your roles or scope changed while this page was open. Refresh to see the
              dashboard you are entitled to now.
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

      {/* One grid, packed into full rows.
          The page used to run a wide reading column beside a narrow rail, each
          stacking until its own contents ran out — which left the shorter of
          the two ending in blank canvas whenever a role resolved to an uneven
          split. Widgets keep their reviewed order and their natural width here;
          `layout.ts` decides which of them share a row and widens a row that
          cannot otherwise close. Panels in a row stretch to a common height, so
          every band has one baseline top and bottom.

          `grid-flow-row-dense` is load-bearing, not decoration: the packer
          places each widget in the earliest row it fits, and the browser has to
          make the same choice or the two disagree. Without it a narrow widget
          later in the DOM cannot back-fill the gap beside a wide one, and the
          row the packer treated as closed renders with a hole in it. */}
      {placed.length > 0 ? (
        <div className="grid grid-flow-row-dense items-stretch gap-6 xl:grid-cols-12">
          {placed.map(({ item, span }) => (
            <div
              key={item.definition.id}
              data-dashboard-slot={item.definition.column}
              // `grid` rather than `block`: the panel inside is a single child
              // and stretches to the row's height instead of leaving the
              // shorter card floating against the top of a tall row.
              className={cn("grid", spanClass(span))}
            >
              <DashboardWidgetSlot resolved={item} page={page} stale={stale} />
            </div>
          ))}
        </div>
      ) : null}

      <PendingModules modules={pending} />
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
