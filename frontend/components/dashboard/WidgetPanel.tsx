import { Link, router } from "@inertiajs/react";
import { Clock, Inbox, Lock, PlugZap, RefreshCw, Unplug } from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";

import { EmptyState } from "@/components/design-system/empty-state";
import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system/surface-card";
import { Button } from "@/components/ui/button";
import type { DashboardWidget, DashboardWidgetProp } from "@/types";

interface WidgetPanelProps<T> {
  title: string;
  propName: DashboardWidgetProp;
  widget: DashboardWidget<T>;
  /**
   * Effective access changed since this payload was computed. The figures are
   * still shown — pulling them out from under a reader mid-read is worse — but
   * they are marked and a refresh is offered.
   */
  stale?: boolean;
  children: (data: T) => ReactNode;
}

/**
 * The shared envelope every dashboard widget renders inside.
 *
 * Six outcomes are distinguishable, because conflating any two of them makes
 * the dashboard lie: `ready`, `empty` (a genuine zero), `unavailable`
 * (the module is not connected), an `error` (a provider that failed this
 * request, which offers a retry of that prop alone), `stale` (shown but no
 * longer trustworthy), and `withheld` (see `WithheldPanel`). Loading is the
 * seventh, and belongs to Inertia's `<Deferred>` fallback.
 */
export function WidgetPanel<T>({
  title,
  propName,
  widget,
  stale = false,
  children,
}: WidgetPanelProps<T>) {
  const [reloading, setReloading] = useState(false);

  if (widget.status === "ready") {
    const content = children(widget.data);
    if (!stale) {
      return content;
    }
    return (
      <div className="grid h-full grid-rows-[auto_1fr] gap-2">
        <StaleNotice />
        {content}
      </div>
    );
  }

  if (widget.status === "empty") {
    const state = widget.emptyState;
    const action =
      state.actionLabel && state.actionHref ? (
        <Button asChild variant="outline" size="sm">
          <Link href={state.actionHref}>{state.actionLabel}</Link>
        </Button>
      ) : undefined;

    return (
      <SurfaceCard className="arrive" data-widget={propName}>
        <PanelHeader title={title} />
        <SurfaceCardContent>
          <EmptyState
            compact
            icon={Inbox}
            title={state.title}
            description={state.description}
            actions={action}
          />
        </SurfaceCardContent>
      </SurfaceCard>
    );
  }

  const state = widget.unavailable;
  const retry = state.retryable ? (
    <Button
      variant="outline"
      size="sm"
      disabled={reloading}
      onClick={() =>
        router.reload({
          only: [propName],
          onStart: () => setReloading(true),
          onFinish: () => setReloading(false),
        })
      }
    >
      <RefreshCw className={reloading ? "animate-spin" : undefined} aria-hidden />
      {reloading ? "Retrying…" : "Try again"}
    </Button>
  ) : state.actionLabel && state.actionHref ? (
    <Button asChild variant="outline" size="sm">
      <Link href={state.actionHref}>{state.actionLabel}</Link>
    </Button>
  ) : undefined;

  return (
    <SurfaceCard
      className="arrive"
      state={state.retryable ? "error" : "read-only"}
      data-widget={propName}
    >
      <PanelHeader title={title} />
      <SurfaceCardContent>
        {/* Every outcome a panel can end on renders through the same empty
            state, so a dashboard of half-connected modules reads as one
            deliberate page rather than five different apologies. */}
        <EmptyState
          compact
          tone="muted"
          role={state.retryable ? "alert" : "status"}
          icon={state.retryable ? Unplug : PlugZap}
          title={state.retryable ? "Couldn’t load this widget" : "Not connected yet"}
          description={state.reason}
          actions={retry}
        />
      </SurfaceCardContent>
    </SurfaceCard>
  );
}

/**
 * The mark above a widget whose data is no longer current.
 *
 * Deliberately label-only. The page carries one stale banner with the refresh
 * action; repeating that button above ten panels would make the fix look like
 * ten separate jobs.
 */
function StaleNotice() {
  return (
    <p className="text-warning-ink flex items-center gap-1.5 text-xs font-medium">
      <Clock className="size-3.5 shrink-0" aria-hidden />
      Stale — loaded before your access changed
    </p>
  );
}

/**
 * A widget the active profile lays out but the reader has no permission for.
 *
 * Most such widgets are simply omitted — a wall of locked panels is noise. This
 * placeholder is for the few where silence would misdescribe the page: a
 * compliance dashboard missing its compliance panel reads as "nothing to
 * review" rather than "not yours to see". It states the gap and names no
 * figure, no count, and no permission codename.
 */
export function WithheldPanel({
  title,
  propName,
}: {
  title: string;
  propName: DashboardWidgetProp;
}) {
  return (
    <SurfaceCard className="arrive" state="read-only" data-widget={propName}>
      <PanelHeader title={title} />
      <SurfaceCardContent>
        <EmptyState
          compact
          tone="muted"
          role="status"
          icon={Lock}
          title="Restricted"
          description="This panel is part of your dashboard, but your access does not cover it. Ask an administrator if you need it."
        />
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
