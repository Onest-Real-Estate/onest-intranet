import { Banknote, CalendarClock, CircleAlert, Handshake } from "lucide-react";

import { IconWell } from "@/components/IconWell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { DashboardStat, DashboardStats } from "@/types";

const CARDS: {
  key: keyof DashboardStats;
  title: string;
  icon: typeof Handshake;
}[] = [
  { key: "activeTransactions", title: "Active transactions", icon: Handshake },
  { key: "upcomingClosings", title: "Upcoming closings", icon: CalendarClock },
  { key: "pendingTasks", title: "Pending tasks", icon: CircleAlert },
  { key: "commissionYtd", title: "Commission YTD", icon: Banknote },
];

function toneClass(tone: DashboardStat["tone"]): string {
  if (tone === "alert") {
    return "text-destructive";
  }
  if (tone === "warning") {
    return "text-warning-foreground";
  }
  if (tone === "success") {
    return "text-success";
  }
  return "text-muted-foreground";
}

export function StatCards({ stats }: { stats: DashboardStats }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {CARDS.map((card) => {
        const stat = stats[card.key];
        return (
          <Card key={card.key}>
            <CardHeader className="flex flex-row items-center justify-between gap-2 pb-2">
              <CardTitle className="text-muted-foreground text-sm font-medium">
                {card.title}
              </CardTitle>
              <IconWell icon={card.icon} className="size-9" />
            </CardHeader>
            <CardContent>
              <p className="text-3xl font-semibold tracking-tight">{stat.value}</p>
              <p className={`mt-1 text-xs ${toneClass(stat.tone)}`}>{stat.hint}</p>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

export function StatCardsSkeleton() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {["s1", "s2", "s3", "s4"].map((id) => (
        <Card key={id}>
          <CardHeader>
            <Skeleton className="h-4 w-32" />
          </CardHeader>
          <CardContent className="grid gap-2">
            <Skeleton className="h-8 w-20" />
            <Skeleton className="h-3 w-28" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
