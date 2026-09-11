import { Link } from "@inertiajs/react";
import { ArrowRight } from "lucide-react";

import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
  SurfaceCardMeta,
} from "@/components/design-system/surface-card";
import type { DashboardWidgetProp } from "@/types";

export interface PendingModule {
  /** The widget's Inertia prop, used as a stable key and a test hook. */
  prop: DashboardWidgetProp;
  title: string;
  /** Only when the provider authored one specific to this module. */
  reason?: string;
  actionLabel?: string;
  actionHref?: string;
}

/**
 * Every module that has no data source yet, stated once at the foot of the
 * page.
 *
 * These used to be full panels. A module with nothing behind it rendered the
 * same envelope as a module with data — a heading, an icon well, a centred
 * "Not connected yet", a link — so on a dashboard where four of eight widgets
 * were unbacked, four hundred-odd pixels of apology sat between the reader and
 * the things that did have data, and the two columns ended hundreds of pixels
 * apart because the gaps fell unevenly between them.
 *
 * The honesty was right and is kept: the dashboard still says exactly which
 * modules are missing and still offers the destination each one will have. What
 * changes is the price. A module that cannot show anything costs a line.
 *
 * A widget that *failed* this request is not listed here — that is a retryable
 * error with a retry control, and it stays a panel where the reader can act on
 * it.
 */
export function PendingModules({ modules }: { modules: readonly PendingModule[] }) {
  if (modules.length === 0) {
    return null;
  }

  return (
    <SurfaceCard state="read-only" className="arrive" data-dashboard-band="pending">
      <PanelHeader
        title="Not connected yet"
        description="These panels join your dashboard as their data sources come online. Nothing here is hidden by your access."
        meta={
          <SurfaceCardMeta>
            {modules.length} {modules.length === 1 ? "module" : "modules"}
          </SurfaceCardMeta>
        }
        divided
      />
      <SurfaceCardContent>
        {/* Proximity does the grouping: a title tight above its own line of
            explanation, with a generous gutter between entries. Rules between
            them would make a handful of short facts read as a table of
            records. */}
        {/* Auto-fit rather than a fixed column count: the band is as wide as
            the page and carries anywhere from one module to eight, so the
            entries divide the width they have instead of stranding a lone
            entry beside an empty half. */}
        <ul className="grid grid-cols-[repeat(auto-fit,minmax(15rem,1fr))] gap-x-10 gap-y-5">
          {modules.map((module) => (
            <li key={module.prop} className="min-w-0" data-widget={module.prop}>
              <p className="text-sm leading-5 font-semibold">{module.title}</p>
              {module.reason ? (
                <p className="text-muted-foreground mt-0.5 max-w-measure text-sm leading-5">
                  {module.reason}
                </p>
              ) : null}
              {module.actionHref && module.actionLabel ? (
                <Link
                  href={module.actionHref}
                  className="text-primary focus-visible:ring-ring mt-1.5 inline-flex items-center gap-1 rounded-sm text-sm font-medium hover:underline focus-visible:ring-2 focus-visible:outline-none"
                >
                  {module.actionLabel}
                  <ArrowRight className="size-3.5" aria-hidden />
                </Link>
              ) : null}
            </li>
          ))}
        </ul>
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
