import { Deferred, Head, usePage } from "@inertiajs/react";
import { ActionItems, ActionItemsSkeleton } from "@/components/dashboard/ActionItems";
import {
  ActiveTransactions,
  ActiveTransactionsSkeleton,
} from "@/components/dashboard/ActiveTransactions";
import {
  Announcements,
  AnnouncementsSkeleton,
} from "@/components/dashboard/Announcements";
import { DashboardGreeting } from "@/components/dashboard/DashboardGreeting";
import {
  MarketSnapshot,
  MarketSnapshotSkeleton,
} from "@/components/dashboard/MarketSnapshot";
import { MyDay, MyDaySkeleton } from "@/components/dashboard/MyDay";
import { QuickApps, QuickAppsSkeleton } from "@/components/dashboard/QuickApps";
import {
  QuickDocuments,
  QuickDocumentsSkeleton,
} from "@/components/dashboard/QuickDocuments";
import { StatCards, StatCardsSkeleton } from "@/components/dashboard/StatCards";
import {
  TrainingResources,
  TrainingResourcesSkeleton,
} from "@/components/dashboard/TrainingResources";
import { HubLayout } from "@/components/HubLayout";
import { routes } from "@/lib/routes";
import type { DashboardPageProps } from "@/types";

export default function Dashboard() {
  const {
    user,
    stats,
    quickApps,
    announcements,
    transactions,
    training,
    schedule,
    actionItems,
    market,
    documents,
  } = usePage<DashboardPageProps>().props;

  if (!user) {
    return null;
  }

  // Wider than `page-shell`: the twelve-column widget grid is the point of this
  // screen, but it still needs a ceiling so it does not sprawl on an ultrawide
  // display.
  return (
    <div className="flex flex-1 flex-col gap-10">
      <Head title="Dashboard" />
      <DashboardGreeting user={user} />

      {/* Band: where the day stands, and the tools to act on it. Figures and
          launchers are one thought, so they sit a section apart (24px) rather
          than a page apart. */}
      <div className="flex flex-col gap-6">
        <Deferred data="stats" fallback={<StatCardsSkeleton />}>
          {stats ? <StatCards stats={stats} /> : null}
        </Deferred>
        <Deferred data="quickApps" fallback={<QuickAppsSkeleton />}>
          {quickApps ? <QuickApps apps={quickApps} /> : null}
        </Deferred>
      </div>

      {/*
        Band: the working grid. The rail leads in source order so a phone —
        where the columns collapse into one — opens on today's obligations
        instead of scrolling past news to reach them; `xl:order` puts it back
        on the right once there are two columns to read side by side.
      */}
      <div className="grid gap-6 xl:grid-cols-12">
        <div className="grid gap-6 xl:order-2 xl:col-span-4">
          <Deferred data="schedule" fallback={<MyDaySkeleton />}>
            {schedule ? <MyDay schedule={schedule} /> : null}
          </Deferred>
          <Deferred data="actionItems" fallback={<ActionItemsSkeleton />}>
            {actionItems ? <ActionItems data={actionItems} /> : null}
          </Deferred>
          <Deferred data="market" fallback={<MarketSnapshotSkeleton />}>
            {market ? <MarketSnapshot market={market} /> : null}
          </Deferred>
          <Deferred data="documents" fallback={<QuickDocumentsSkeleton />}>
            {documents ? <QuickDocuments documents={documents} /> : null}
          </Deferred>
        </div>
        <div className="grid gap-6 xl:order-1 xl:col-span-8">
          <Deferred data="announcements" fallback={<AnnouncementsSkeleton />}>
            {announcements ? <Announcements data={announcements} /> : null}
          </Deferred>
          <Deferred data="transactions" fallback={<ActiveTransactionsSkeleton />}>
            {transactions ? <ActiveTransactions transactions={transactions} /> : null}
          </Deferred>
          <Deferred data="training" fallback={<TrainingResourcesSkeleton />}>
            {training ? <TrainingResources training={training} /> : null}
          </Deferred>
        </div>
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
