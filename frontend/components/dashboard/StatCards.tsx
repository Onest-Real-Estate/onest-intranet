import {
  Banknote,
  CalendarClock,
  CircleAlert,
  Handshake,
  Info,
  TrendingDown,
  TrendingUp,
} from "lucide-react";

import { IconWell } from "@/components/IconWell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { DashboardStat, DashboardStats } from "@/types";

const CARDS: {
  key: keyof DashboardStats;
  title: string;
  icon: typeof Handshake;
  /** Plain reading of what the figure counts, shown on the header's info mark. */
  note: string;
}[] = [
  {
    key: "activeTransactions",
    title: "Active transactions",
    icon: Handshake,
    note: "Deals currently open in your pipeline.",
  },
  {
    key: "upcomingClosings",
    title: "Upcoming closings",
    icon: CalendarClock,
    note: "Closings scheduled in the next 30 days.",
  },
  {
    key: "pendingTasks",
    title: "Pending tasks",
    icon: CircleAlert,
    note: "Tasks assigned to you that are not yet complete.",
  },
  {
    key: "commissionYtd",
    title: "Commission YTD",
    icon: Banknote,
    note: "Commission credited to you so far this calendar year.",
  },
];

/**
 * The hint reads as a chip beside the figure rather than as loose text under
 * it. `--warning-foreground` is the ink that sits *on* a warning surface — used
 * as a text colour it renders near-black, so the warning tone would read as no
 * tone at all; `--warning-ink` is the readable text step of that hue.
 */
function toneClass(tone: DashboardStat["tone"]): string {
  if (tone === "alert") {
    return "bg-destructive/10 text-destructive";
  }
  if (tone === "warning") {
    return "bg-warning/20 text-warning-ink";
  }
  if (tone === "success") {
    return "bg-success/15 text-success";
  }
  return "bg-muted text-muted-foreground";
}

/** Rising and falling figures earn an arrow; everything else stays quiet. */
function toneIcon(tone: DashboardStat["tone"], hint: string) {
  if (hint.startsWith("+")) {
    return TrendingUp;
  }
  if (hint.startsWith("-")) {
    return TrendingDown;
  }
  return tone === "alert" || tone === "warning" ? CircleAlert : null;
}

export function StatCards({ stats }: { stats: DashboardStats }) {
  return (
    <div className="arrive grid grid-cols-2 gap-4 xl:grid-cols-4">
      {CARDS.map((card) => {
        const stat = stats[card.key];
        const HintIcon = toneIcon(stat.tone, stat.hint);
        return (
          <Card key={card.key} className="gap-4 py-5">
            <CardHeader className="flex flex-row items-center justify-between gap-2">
              <CardTitle
                asChild
                className="text-muted-foreground flex min-w-0 items-center gap-2.5 text-sm font-medium"
              >
                <h2>
                  <IconWell
                    icon={card.icon}
                    className="size-8"
                    iconClassName="size-4"
                  />
                  <span className="min-w-0 leading-tight">{card.title}</span>
                </h2>
              </CardTitle>
              <Tooltip>
                <TooltipTrigger
                  // Hover-only affordance, and on a phone it would crowd a
                  // label that already wraps — the label names the metric.
                  className="text-muted-foreground/70 hover:text-foreground focus-visible:ring-ring hidden shrink-0 rounded-full transition-colors focus-visible:ring-2 focus-visible:outline-none sm:inline-flex"
                  aria-label={`What ${card.title} counts`}
                >
                  <Info className="size-4" strokeWidth={1.5} />
                </TooltipTrigger>
                <TooltipContent className="max-w-56">{card.note}</TooltipContent>
              </Tooltip>
            </CardHeader>
            <CardContent className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1.5">
              <p className="text-3xl font-semibold tracking-tight tabular-nums">
                {stat.value}
              </p>
              <span
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${toneClass(stat.tone)}`}
              >
                {HintIcon ? <HintIcon className="size-3.5" aria-hidden /> : null}
                {stat.hint}
              </span>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

export function StatCardsSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
      {["s1", "s2", "s3", "s4"].map((id) => (
        <Card key={id} className="gap-4 py-5">
          <CardHeader className="flex flex-row items-center gap-2.5">
            <Skeleton className="size-8 shrink-0 rounded-lg" />
            <Skeleton className="h-4 w-24" />
          </CardHeader>
          <CardContent className="flex items-center gap-2.5">
            <Skeleton className="h-8 w-16" />
            <Skeleton className="h-5 w-24 rounded-full" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
