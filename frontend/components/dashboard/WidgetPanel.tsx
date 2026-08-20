import { Link, router } from "@inertiajs/react";
import { Inbox, RefreshCw, Unplug } from "lucide-react";
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
  children: (data: T) => ReactNode;
}

/** Render the shared envelope states without obscuring each widget's ready UI. */
export function WidgetPanel<T>({
  title,
  propName,
  widget,
  children,
}: WidgetPanelProps<T>) {
  const [reloading, setReloading] = useState(false);

  if (widget.status === "ready") {
    return children(widget.data);
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
        <section
          role={state.retryable ? "alert" : "status"}
          className="flex flex-col items-start gap-3 py-3"
        >
          <span className="bg-muted text-muted-foreground grid size-9 place-items-center rounded-lg">
            <Unplug className="size-4" aria-hidden />
          </span>
          <div className="max-w-md">
            <h3 className="text-sm font-semibold">
              {state.retryable ? "Couldn’t load this widget" : "Not connected yet"}
            </h3>
            <p className="text-muted-foreground mt-1 text-sm leading-5">
              {state.reason}
            </p>
          </div>
          {retry}
        </section>
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
