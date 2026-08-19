import { MetricCard, MetricGroup } from "@/components/design-system/metric-card";
import type { DashboardStat, DashboardStats } from "@/types";

function trend(hint: string): "up" | "down" | "flat" {
  if (hint.startsWith("+")) return "up";
  if (hint.startsWith("-")) return "down";
  return "flat";
}

function tone(
  value: DashboardStat["tone"],
): "neutral" | "success" | "warning" | "destructive" {
  if (value === "alert") return "destructive";
  if (value === "default") return "neutral";
  return value;
}

function Stat({ label, stat }: { label: string; stat: DashboardStat }) {
  return (
    <MetricCard
      label={label}
      value={stat.value}
      hint={stat.hint}
      trend={trend(stat.hint)}
      tone={tone(stat.tone)}
    />
  );
}

export function StatCards({ stats }: { stats: DashboardStats }) {
  return (
    <div className="arrive grid gap-4 xl:grid-cols-2">
      <MetricGroup title="Pipeline">
        <Stat label="Active transactions" stat={stats.activeTransactions} />
        <Stat label="Commission YTD" stat={stats.commissionYtd} />
      </MetricGroup>
      <MetricGroup title="Deal activity">
        <Stat label="Upcoming closings" stat={stats.upcomingClosings} />
        <Stat label="Pending tasks" stat={stats.pendingTasks} />
      </MetricGroup>
    </div>
  );
}

export function StatCardsSkeleton() {
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      {["pipeline", "activity"].map((group) => (
        <MetricGroup key={group} title="Loading metrics">
          <MetricCard label="Loading" value="—" loading />
          <MetricCard label="Loading" value="—" loading />
        </MetricGroup>
      ))}
    </div>
  );
}
