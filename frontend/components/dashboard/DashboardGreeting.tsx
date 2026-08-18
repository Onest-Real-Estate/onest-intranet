import { Sparkles } from "lucide-react";

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
  const hour = new Date().getHours();
  return (
    <div>
      <h1 className="flex items-center gap-2 text-[32px] font-bold tracking-[-0.02em]">
        <Sparkles
          className="text-[var(--brand-gold)] size-7 shrink-0"
          strokeWidth={1.5}
        />
        {greetingForHour(hour)}, {firstName(user.name)}
      </h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Here&apos;s what&apos;s happening at ONEST today.
      </p>
    </div>
  );
}
