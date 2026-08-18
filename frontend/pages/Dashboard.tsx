import { Deferred, usePage } from "@inertiajs/react";
import type { ReactNode } from "react";
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

  return (
    <div className="flex flex-1 flex-col gap-6 px-4 py-6 sm:px-6">
      <DashboardGreeting user={user} />

      <Deferred data="stats" fallback={<StatCardsSkeleton />}>
        {stats ? <StatCards stats={stats} /> : null}
      </Deferred>

      <div className="grid gap-6 xl:grid-cols-12">
        <div className="grid gap-6 xl:col-span-8">
          <Deferred data="quickApps" fallback={<QuickAppsSkeleton />}>
            {quickApps ? <QuickApps apps={quickApps} /> : null}
          </Deferred>
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
        <div className="grid gap-6 xl:col-span-4">
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
      </div>
    </div>
  );
}

Dashboard.layout = (page: ReactNode) => <HubLayout>{page}</HubLayout>;
