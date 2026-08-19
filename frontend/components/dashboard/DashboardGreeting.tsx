import { PageHeader } from "@/components/design-system/page-header";
import type { DashboardGreeting as Greeting, User } from "@/types";

export function DashboardGreeting({
  greeting,
  user,
}: {
  greeting: Greeting;
  user: User;
}) {
  // The date and role are facts about the page, not a control, so they sit in
  // the meta line as plain text rather than in a chip that invites a click.
  return (
    <PageHeader
      title={`${greeting.salutation}, ${greeting.name}`}
      meta={
        <>
          <time dateTime={greeting.dateIso}>{greeting.dateLabel}</time>
          <span aria-hidden>·</span>
          <span>{user.roleLabel}</span>
        </>
      }
    />
  );
}
