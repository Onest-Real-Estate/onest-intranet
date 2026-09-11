import { Link } from "@inertiajs/react";
import { ArrowRight } from "lucide-react";

import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
  SurfaceCardMeta,
} from "@/components/design-system/surface-card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { DashboardStages } from "@/types";
import type { StatusTone } from "@/types/design-system";

const toneDot: Record<StatusTone, string> = {
  neutral: "bg-muted-foreground/40",
  info: "bg-info",
  success: "bg-success",
  warning: "bg-warning",
  destructive: "bg-destructive",
};

/**
 * A staged count — an onboarding funnel, a closing pipeline, a support queue
 * by priority. One presentation serves every administrative funnel so a new
 * one is a registry row and a provider, not another component.
 *
 * Every stage carries its label as text; tone qualifies the figure and is
 * never the only thing distinguishing "at risk" from "on track".
 */
export function StageFunnel({
  title,
  data,
  action,
}: {
  title: string;
  data: DashboardStages;
  action?: React.ReactNode;
}) {
  return (
    <SurfaceCard className="arrive">
      <PanelHeader
        title={title}
        meta={<SurfaceCardMeta>{data.caption}</SurfaceCardMeta>}
        // The provider sends the list this funnel counts; an explicit `action`
        // still wins for a caller that needs a different control.
        action={
          action ??
          (data.viewAllHref ? (
            <Button asChild variant="ghost" size="sm" className="gap-1">
              <Link href={data.viewAllHref}>
                View all
                <ArrowRight className="size-3.5" strokeWidth={1.5} aria-hidden />
              </Link>
            </Button>
          ) : undefined)
        }
      />
      <SurfaceCardContent>
        <dl className="grid gap-2 sm:grid-cols-2">
          {data.stages.map((stage) => (
            <div
              key={stage.key}
              className="bg-card min-w-0 rounded-lg border px-3 py-3"
            >
              <dt className="text-muted-foreground flex items-start justify-between gap-3 text-xs font-medium">
                <span className="min-w-0 text-pretty">{stage.label}</span>
                {/* Tone qualifies the figure; the stage's own label above is
                    what carries the meaning, so the swatch is decorative. */}
                {stage.tone !== "neutral" ? (
                  <span
                    className={cn(
                      "mt-1 size-2 shrink-0 rounded-full",
                      toneDot[stage.tone],
                    )}
                    aria-hidden
                  />
                ) : null}
              </dt>
              <dd
                className={cn(
                  "mt-1 text-2xl leading-8 font-semibold tracking-[-0.02em] tabular-nums",
                  stage.tone === "destructive" && "text-destructive",
                )}
              >
                {stage.value}
              </dd>
              {stage.hint ? (
                <dd className="text-muted-foreground mt-0.5 text-xs">{stage.hint}</dd>
              ) : null}
            </div>
          ))}
        </dl>
      </SurfaceCardContent>
    </SurfaceCard>
  );
}

export function StageFunnelSkeleton({ title }: { title: string }) {
  return (
    <SurfaceCard state="loading">
      <PanelHeader title={title} />
      <SurfaceCardContent className="grid gap-2 sm:grid-cols-2">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
