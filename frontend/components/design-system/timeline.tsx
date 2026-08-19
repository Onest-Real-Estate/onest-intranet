import type { LucideIcon } from "lucide-react";
import type * as React from "react";

import { cn } from "@/lib/utils";
import type { StatusTone } from "@/types/design-system";

export interface TimelineItem {
  id: string;
  title: string;
  description?: string;
  meta?: string;
  tone?: StatusTone;
  current?: boolean;
  /**
   * Optional mark in place of the dot — a check for something completed, for
   * instance. The dot is the default because most timeline entries are simply
   * points in a sequence, and a check on all of them would claim otherwise.
   */
  icon?: LucideIcon;
}

const dotTone: Record<StatusTone, string> = {
  neutral: "bg-muted-foreground/45 ring-muted-foreground/12",
  info: "bg-info ring-info/15",
  success: "bg-success ring-success/15",
  warning: "bg-warning ring-warning/20",
  destructive: "bg-destructive ring-destructive/15",
};

const iconTone: Record<StatusTone, string> = {
  neutral: "text-muted-foreground",
  info: "text-info",
  success: "text-success",
  warning: "text-warning-ink",
  destructive: "text-destructive",
};

export function Timeline({
  items,
  className,
  ...props
}: Omit<React.ComponentProps<"ol">, "children"> & { items: TimelineItem[] }) {
  return (
    <ol className={cn("grid", className)} {...props}>
      {items.map((item, index) => {
        const tone = item.tone ?? "neutral";
        const Icon = item.icon;
        return (
          <li
            key={item.id}
            aria-current={item.current ? "step" : undefined}
            className="relative grid grid-cols-[1.25rem_minmax(0,1fr)] gap-3 pb-5 last:pb-0"
          >
            {index < items.length - 1 ? (
              <span
                className="bg-border absolute top-6 bottom-0 left-2.5 w-px -translate-x-1/2"
                aria-hidden
              />
            ) : null}
            <span className="relative z-1 grid h-5 place-items-center">
              {Icon ? (
                <Icon className={cn("size-4", iconTone[tone])} aria-hidden />
              ) : (
                <span
                  className={cn(
                    "size-2.5 rounded-full ring-4",
                    dotTone[tone],
                    item.current && "ring-[6px]",
                  )}
                  aria-hidden
                />
              )}
            </span>
            <div className="min-w-0">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                <p className="text-sm font-semibold">{item.title}</p>
                {item.meta ? (
                  <p className="text-muted-foreground text-xs tabular-nums">
                    {item.meta}
                  </p>
                ) : null}
              </div>
              {item.description ? (
                <p className="text-muted-foreground mt-0.5 text-sm leading-5">
                  {item.description}
                </p>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
