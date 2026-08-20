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
import { MetricCards, MetricCardsSkeleton } from "@/components/dashboard/MetricCards";
import { MyDay, MyDaySkeleton } from "@/components/dashboard/MyDay";
import { QuickApps, QuickAppsSkeleton } from "@/components/dashboard/QuickApps";
import {
  QuickDocuments,
  QuickDocumentsSkeleton,
} from "@/components/dashboard/QuickDocuments";
import {
  TrainingResources,
  TrainingResourcesSkeleton,
} from "@/components/dashboard/TrainingResources";
import { WidgetPanel } from "@/components/dashboard/WidgetPanel";
import { HubLayout } from "@/components/HubLayout";
import { routes } from "@/lib/routes";
import type { DashboardPageProps } from "@/types";

export default function Dashboard() {
  const {
    user,
    greeting,
    metrics,
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
      <DashboardGreeting greeting={greeting} user={user} />

      {/* Band: where the day stands, and the tools to act on it. Figures and
          launchers are one thought, so they sit a section apart (24px) rather
          than a page apart. */}
      <div className="flex flex-col gap-6">
        <Deferred data="metrics" fallback={<MetricCardsSkeleton />}>
          {metrics ? (
            <WidgetPanel title="Performance" propName="metrics" widget={metrics}>
              {(data) => <MetricCards metrics={data} />}
            </WidgetPanel>
          ) : null}
        </Deferred>
        <Deferred data="quickApps" fallback={<QuickAppsSkeleton />}>
          {quickApps ? (
            <WidgetPanel title="Quick access" propName="quickApps" widget={quickApps}>
              {(data) => <QuickApps apps={data} />}
            </WidgetPanel>
          ) : null}
        </Deferred>
      </div>

      {/*
        Band: the working grid. The rail leads in source order so a phone —
        where the columns collapse into one — opens on today's obligations
        instead of scrolling past news to reach them; `xl:order` puts it back
        on the right once there are two columns to read side by side.
      */}
      <div className="grid items-start gap-6 xl:grid-cols-12">
        <div className="grid content-start gap-6 xl:order-2 xl:col-span-4">
          <Deferred data="schedule" fallback={<MyDaySkeleton />}>
            {schedule ? (
              <WidgetPanel title="My day" propName="schedule" widget={schedule}>
                {(data) => <MyDay schedule={data} />}
              </WidgetPanel>
            ) : null}
          </Deferred>
          <Deferred data="actionItems" fallback={<ActionItemsSkeleton />}>
            {actionItems ? (
              <WidgetPanel
                title="Action items"
                propName="actionItems"
                widget={actionItems}
              >
                {(data) => <ActionItems data={data} />}
              </WidgetPanel>
            ) : null}
          </Deferred>
          <Deferred data="market" fallback={<MarketSnapshotSkeleton />}>
            {market ? (
              <WidgetPanel title="Market snapshot" propName="market" widget={market}>
                {(data) => <MarketSnapshot market={data} />}
              </WidgetPanel>
            ) : null}
          </Deferred>
          <Deferred data="documents" fallback={<QuickDocumentsSkeleton />}>
            {documents ? (
              <WidgetPanel
                title="Quick documents"
                propName="documents"
                widget={documents}
              >
                {(data) => <QuickDocuments documents={data} />}
              </WidgetPanel>
            ) : null}
          </Deferred>
        </div>
        <div className="grid content-start gap-6 xl:order-1 xl:col-span-8">
          <Deferred data="announcements" fallback={<AnnouncementsSkeleton />}>
            {announcements ? (
              <WidgetPanel
                title="News & announcements"
                propName="announcements"
                widget={announcements}
              >
                {(data) => <Announcements data={data} />}
              </WidgetPanel>
            ) : null}
          </Deferred>
          <Deferred data="transactions" fallback={<ActiveTransactionsSkeleton />}>
            {transactions ? (
              <WidgetPanel
                title="Active transactions"
                propName="transactions"
                widget={transactions}
              >
                {(data) => <ActiveTransactions transactions={data} />}
              </WidgetPanel>
            ) : null}
          </Deferred>
          <Deferred data="training" fallback={<TrainingResourcesSkeleton />}>
            {training ? (
              <WidgetPanel
                title="Training & resources"
                propName="training"
                widget={training}
              >
                {(data) => <TrainingResources training={data} />}
              </WidgetPanel>
            ) : null}
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
