import { Head, Link, router, usePage } from "@inertiajs/react";
import { AlertTriangle, Inbox, RefreshCw } from "lucide-react";
import { useState } from "react";

import { ActionItems } from "@/components/dashboard/ActionItems";
import { PageHeader } from "@/components/design-system";
import { EmptyState } from "@/components/design-system/empty-state";
import {
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system/surface-card";
import { HubLayout } from "@/components/HubLayout";
import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";
import type { ActionItemsQueuePageProps } from "@/types";

export default function ActionItemsQueue() {
  const { queue, emptyState, unavailable, partialFailure } =
    usePage<ActionItemsQueuePageProps>().props;
  const [reloading, setReloading] = useState(false);

  return (
    <div className="mx-auto grid w-full max-w-3xl gap-6 py-6">
      <Head title="Action items" />
      <PageHeader
        title="Action items"
        description="Work assigned to you or waiting on your action, ordered by urgency."
      />

      {partialFailure ? (
        <SurfaceCard state="error">
          <SurfaceCardContent className="flex items-start gap-3 text-sm">
            <AlertTriangle
              className="text-destructive mt-0.5 size-4 shrink-0"
              strokeWidth={1.5}
              aria-hidden
            />
            <p>
              Some action sources could not be checked just now. Showing what loaded
              successfully.
            </p>
          </SurfaceCardContent>
        </SurfaceCard>
      ) : null}

      {unavailable ? (
        <SurfaceCard state={unavailable.retryable ? "error" : "read-only"}>
          <SurfaceCardContent>
            <EmptyState
              compact
              icon={unavailable.retryable ? AlertTriangle : Inbox}
              title="Action items unavailable"
              description={unavailable.reason}
              actions={
                unavailable.retryable ? (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={reloading}
                    onClick={() =>
                      router.reload({
                        onStart: () => setReloading(true),
                        onFinish: () => setReloading(false),
                      })
                    }
                  >
                    <RefreshCw
                      className={reloading ? "animate-spin" : undefined}
                      aria-hidden
                    />
                    {reloading ? "Retrying…" : "Try again"}
                  </Button>
                ) : undefined
              }
            />
          </SurfaceCardContent>
        </SurfaceCard>
      ) : null}

      {emptyState && !queue?.items.length ? (
        <SurfaceCard>
          <SurfaceCardContent>
            <EmptyState
              compact
              icon={Inbox}
              title={emptyState.title}
              description={emptyState.description}
              actions={
                emptyState.actionLabel && emptyState.actionHref ? (
                  <Button asChild variant="outline" size="sm">
                    <Link href={emptyState.actionHref}>{emptyState.actionLabel}</Link>
                  </Button>
                ) : undefined
              }
            />
          </SurfaceCardContent>
        </SurfaceCard>
      ) : null}

      {queue && queue.items.length > 0 ? <ActionItems data={queue} /> : null}
    </div>
  );
}

ActionItemsQueue.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Action items",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Action items", href: routes.action_items_queue() },
        ],
        back: { label: "Back to dashboard", href: routes.dashboard() },
      },
      variant: "standard",
    },
  ] as const;
