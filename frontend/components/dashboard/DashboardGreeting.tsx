import { CalendarDays } from "lucide-react";

import type { User } from "@/types";

function greetingForHour(hour: number): string {
  if (hour < 12) {
    return "Good morning";
  }
  if (hour < 17) {
    return "Good afternoon";
  }
  return "Good evening";
}

function firstName(name: string): string {
  return name.split(/\s+/).filter(Boolean)[0] ?? name;
}

export function DashboardGreeting({ user }: { user: User }) {
  const now = new Date();
  const hour = now.getHours();
  const today = now.toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  });

  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold tracking-[-0.02em] sm:text-[32px]">
          {greetingForHour(hour)}, {firstName(user.name)}
        </h1>
        <p className="text-muted-foreground mt-1.5 text-sm">
          Here&apos;s what&apos;s happening at ONEST today.
        </p>
      </div>
      {/* The reference's date-range control, reduced to the one fact this
          screen can actually state: which day it is showing. */}
      <p className="text-muted-foreground bg-card flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm">
        <CalendarDays className="size-4" strokeWidth={1.5} aria-hidden />
        {today}
      </p>
    </div>
  );
}
