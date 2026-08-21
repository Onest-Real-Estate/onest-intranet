import { Deferred } from "@inertiajs/react";
import type { ReactNode } from "react";

import { ActionItems, ActionItemsSkeleton } from "@/components/dashboard/ActionItems";
import {
  ActiveTransactions,
  ActiveTransactionsSkeleton,
} from "@/components/dashboard/ActiveTransactions";
import {
  ActivityFeed,
  ActivityFeedSkeleton,
} from "@/components/dashboard/ActivityFeed";
import {
  Announcements,
  AnnouncementsSkeleton,
} from "@/components/dashboard/Announcements";
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
import { StageFunnel, StageFunnelSkeleton } from "@/components/dashboard/StageFunnel";
import {
  TrainingResources,
  TrainingResourcesSkeleton,
} from "@/components/dashboard/TrainingResources";
import {
  UtilizationMeter,
  UtilizationMeterSkeleton,
} from "@/components/dashboard/UtilizationMeter";
import { WidgetPanel, WithheldPanel } from "@/components/dashboard/WidgetPanel";
import { WorkQueue, WorkQueueSkeleton } from "@/components/dashboard/WorkQueue";
import { PREVIEW_WIDGETS } from "@/lib/dashboard/preview";
import type { ResolvedDashboardWidget } from "@/lib/dashboard/resolve";
import type { DashboardWidgetDefinition } from "@/lib/dashboard/widget-registry";
import type { DashboardPageProps, DashboardWidget } from "@/types";

interface SlotProps<T> {
  definition: DashboardWidgetDefinition;
  /** Undefined while a deferred prop is still in flight. */
  widget: DashboardWidget<T> | undefined;
  skeleton: ReactNode;
  render: (data: T) => ReactNode;
  stale: boolean;
}

/**
 * Choose between the server's envelope and the preview fixture.
 *
 * A `ready` server envelope always wins, whatever the registry says: real data
 * must never end up hidden behind a fixture because someone forgot to flip
 * `backed`. Otherwise an unbacked widget shows its preview, and a backed one
 * shows whatever the provider actually said — including empty and failed.
 */
function envelope<T>(
  definition: DashboardWidgetDefinition,
  fromServer: DashboardWidget<T> | undefined,
  preview: DashboardWidget<T>,
): DashboardWidget<T> | undefined {
  if (fromServer?.status === "ready" || definition.backed) {
    return fromServer;
  }
  return preview;
}

/**
 * One widget's independent lifecycle.
 *
 * Each slot owns its own loading fallback, its own envelope, and its own retry,
 * so a provider that fails takes down one card and nothing else — the reason
 * the page never awaits a combined payload.
 */
function Slot<T>({ definition, widget, skeleton, render, stale }: SlotProps<T>) {
  const panel = widget ? (
    <WidgetPanel
      title={definition.title}
      propName={definition.prop}
      widget={widget}
      stale={stale}
      preview={widget.meta.preview === true}
    >
      {render}
    </WidgetPanel>
  ) : null;

  // An unbacked widget has no deferred prop to wait on: what it shows is
  // already in hand, or there is nothing to show.
  if (!definition.backed) {
    return panel;
  }
  return (
    <Deferred data={definition.prop} fallback={skeleton}>
      {panel}
    </Deferred>
  );
}

/**
 * Render one resolved widget from the page's props.
 *
 * The switch is the only place a widget id meets a component. Profiles store
 * ids, never component names, so this mapping is the allowlist in code form —
 * an id that is not a case here renders nothing at all.
 */
export function DashboardWidgetSlot({
  resolved,
  page,
  stale,
}: {
  resolved: ResolvedDashboardWidget;
  page: DashboardPageProps;
  stale: boolean;
}) {
  const { definition, withheld } = resolved;
  if (withheld) {
    return <WithheldPanel title={definition.title} propName={definition.prop} />;
  }
  const title = definition.title;

  switch (definition.id) {
    case "performance":
      return (
        <Slot
          definition={definition}
          widget={page.metrics}
          skeleton={<MetricCardsSkeleton />}
          stale={stale}
          render={(data) => <MetricCards metrics={data} />}
        />
      );
    case "quickAccess":
      return (
        <Slot
          definition={definition}
          widget={page.quickApps}
          skeleton={<QuickAppsSkeleton />}
          stale={stale}
          render={(data) => (
            <QuickApps
              apps={data}
              csrfToken={page.csrfToken}
              truncated={page.quickApps?.meta.truncated === true}
            />
          )}
        />
      );
    case "myDay":
      return (
        <Slot
          definition={definition}
          widget={page.schedule}
          skeleton={<MyDaySkeleton />}
          stale={stale}
          render={(data) => <MyDay schedule={data} />}
        />
      );
    case "actionItems":
      return (
        <Slot
          definition={definition}
          widget={page.actionItems}
          skeleton={<ActionItemsSkeleton />}
          stale={stale}
          render={(data) => <ActionItems data={data} />}
        />
      );
    case "activeTransactions":
      return (
        <Slot
          definition={definition}
          widget={page.transactions}
          skeleton={<ActiveTransactionsSkeleton />}
          stale={stale}
          render={(data) => <ActiveTransactions transactions={data} />}
        />
      );
    case "announcements":
      return (
        <Slot
          definition={definition}
          widget={envelope(
            definition,
            page.announcements,
            PREVIEW_WIDGETS.announcements,
          )}
          skeleton={<AnnouncementsSkeleton />}
          stale={stale}
          render={(data) => <Announcements data={data} />}
        />
      );
    case "training":
      return (
        <Slot
          definition={definition}
          widget={page.training}
          skeleton={<TrainingResourcesSkeleton />}
          stale={stale}
          render={(data) => <TrainingResources training={data} />}
        />
      );
    case "marketSnapshot":
      return (
        <Slot
          definition={definition}
          widget={page.market}
          skeleton={<MarketSnapshotSkeleton />}
          stale={stale}
          render={(data) => <MarketSnapshot market={data} />}
        />
      );
    case "quickDocuments":
      return (
        <Slot
          definition={definition}
          widget={page.documents}
          skeleton={<QuickDocumentsSkeleton />}
          stale={stale}
          render={(data) => <QuickDocuments documents={data} />}
        />
      );
    case "agentOnboarding":
      return (
        <Slot
          definition={definition}
          widget={envelope(
            definition,
            page.agentOnboarding,
            PREVIEW_WIDGETS.agentOnboarding,
          )}
          skeleton={<StageFunnelSkeleton title={title} />}
          stale={stale}
          render={(data) => <StageFunnel title={title} data={data} />}
        />
      );
    case "closingPipeline":
      return (
        <Slot
          definition={definition}
          widget={envelope(
            definition,
            page.closingPipeline,
            PREVIEW_WIDGETS.closingPipeline,
          )}
          skeleton={<StageFunnelSkeleton title={title} />}
          stale={stale}
          render={(data) => <StageFunnel title={title} data={data} />}
        />
      );
    case "contractsAwaitingSignature":
      return (
        <Slot
          definition={definition}
          widget={envelope(
            definition,
            page.contractsAwaitingSignature,
            PREVIEW_WIDGETS.contractsAwaitingSignature,
          )}
          skeleton={<WorkQueueSkeleton title={title} />}
          stale={stale}
          render={(data) => <WorkQueue title={title} data={data} />}
        />
      );
    case "complianceExceptions":
      return (
        <Slot
          definition={definition}
          widget={envelope(
            definition,
            page.complianceExceptions,
            PREVIEW_WIDGETS.complianceExceptions,
          )}
          skeleton={<WorkQueueSkeleton title={title} />}
          stale={stale}
          render={(data) => <WorkQueue title={title} data={data} />}
        />
      );
    case "teamTasks":
      return (
        <Slot
          definition={definition}
          widget={envelope(definition, page.teamTasks, PREVIEW_WIDGETS.teamTasks)}
          skeleton={<WorkQueueSkeleton title={title} />}
          stale={stale}
          render={(data) => <WorkQueue title={title} data={data} />}
        />
      );
    case "overdueInventory":
      return (
        <Slot
          definition={definition}
          widget={envelope(
            definition,
            page.overdueInventory,
            PREVIEW_WIDGETS.overdueInventory,
          )}
          skeleton={<WorkQueueSkeleton title={title} />}
          stale={stale}
          render={(data) => <WorkQueue title={title} data={data} />}
        />
      );
    case "roomUtilization":
      return (
        <Slot
          definition={definition}
          widget={envelope(
            definition,
            page.roomUtilization,
            PREVIEW_WIDGETS.roomUtilization,
          )}
          skeleton={<UtilizationMeterSkeleton title={title} />}
          stale={stale}
          render={(data) => <UtilizationMeter title={title} data={data} />}
        />
      );
    case "operationalActivity":
      return (
        <Slot
          definition={definition}
          widget={envelope(
            definition,
            page.operationalActivity,
            PREVIEW_WIDGETS.operationalActivity,
          )}
          skeleton={<ActivityFeedSkeleton title={title} />}
          stale={stale}
          render={(data) => <ActivityFeed title={title} data={data} />}
        />
      );
    case "supportQueue":
      return (
        <Slot
          definition={definition}
          widget={envelope(definition, page.supportQueue, PREVIEW_WIDGETS.supportQueue)}
          skeleton={<WorkQueueSkeleton title={title} />}
          stale={stale}
          render={(data) => <WorkQueue title={title} data={data} />}
        />
      );
    case "feedbackSignals":
      return (
        <Slot
          definition={definition}
          widget={envelope(
            definition,
            page.feedbackSignals,
            PREVIEW_WIDGETS.feedbackSignals,
          )}
          skeleton={<WorkQueueSkeleton title={title} />}
          stale={stale}
          render={(data) => <WorkQueue title={title} data={data} />}
        />
      );
  }
}
