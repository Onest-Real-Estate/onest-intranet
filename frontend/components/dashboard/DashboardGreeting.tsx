import type { ReactNode } from "react";

import { PageHeader } from "@/components/design-system/page-header";
import type { DashboardGreeting as Greeting, User } from "@/types";

export function DashboardGreeting({
  greeting,
  user,
  actions,
}: {
  greeting: Greeting;
  user: User;
  /** Scope and profile controls, so the masthead is one block and one rule. */
  actions?: ReactNode;
}) {
  // The date and role are facts about the page, not a control, so they sit in
  // the meta line as plain text rather than in a chip that invites a click.
  return (
    <PageHeader
      title={`${greeting.salutation}, ${greeting.name}`}
      actions={actions}
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
