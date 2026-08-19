import { PageHeader } from "@/components/design-system/page-header";
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
  const today = now.toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  });

  // The date and role are facts about the page, not a control, so they sit in
  // the meta line as plain text rather than in a chip that invites a click.
  return (
    <PageHeader
      title={`${greetingForHour(now.getHours())}, ${firstName(user.name)}`}
      meta={
        <>
          <span>{today}</span>
          <span aria-hidden>·</span>
          <span>{user.roleLabel}</span>
        </>
      }
    />
  );
}
