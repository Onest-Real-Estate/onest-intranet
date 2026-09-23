import { Link, usePage } from "@inertiajs/react";
import { UserPlus } from "lucide-react";

import { type PageTab, PageTabs } from "@/components/design-system";
import { Button } from "@/components/ui/button";
import { hasPermission } from "@/lib/permissions";
import { routes } from "@/lib/routes";
import type { PageProps } from "@/types";

export type PeopleTabKey = "users" | "roles" | "new-agents";

/** Each tab and the grant that opens it — the same pairs the server's
 *  `people_hub` redirect walks, in the same order. */
const PEOPLE_TABS: (PageTab & { key: PeopleTabKey; permission: string })[] = [
  {
    key: "users",
    label: "Users",
    href: routes.admin_users(),
    permission: "web.view_users",
  },
  {
    key: "roles",
    label: "Roles & permissions",
    href: routes.admin_assign_roles(),
    permission: "web.assign_user_roles",
  },
  {
    key: "new-agents",
    label: "New agents",
    href: routes.admin_new_agents(),
    permission: "web.view_new_agents",
  },
];

/**
 * The top of every People page: one title, the tabs this reader may open, and
 * the one section-wide action. Replaces four sidebar entries with one.
 *
 * A tab is hidden, not disabled, when the reader lacks its grant — each page
 * still enforces its own permission on the server, so hiding is presentation
 * only.
 */
export function PeopleHeader({
  current,
  scope,
}: {
  current: PeopleTabKey;
  /** The reader's reach, e.g. "Brokerage-wide". Every list below is cut to it. */
  scope: string;
}) {
  const { user } = usePage<PageProps>().props;
  const tabs = PEOPLE_TABS.filter((tab) =>
    hasPermission(user, { all: [tab.permission] }),
  );
  const canAdd = hasPermission(user, { all: ["web.add_users"] });

  return (
    <header className="grid gap-4">
      {/* One line for every tab: switching tabs changes the list, never the
          masthead, so nothing above the tabs moves. */}
      <div className="grid gap-1">
        <h1 className="text-2xl leading-8 font-bold tracking-[-0.02em]">People</h1>
        <p className="text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-1 text-sm leading-6">
          Accounts, roles, and new-agent onboarding.
          <span className="bg-chip-neutral border-chip-neutral-edge text-foreground inline-flex h-6 items-center rounded-sm border px-2 text-xs font-medium">
            {scope}
          </span>
        </p>
      </div>
      <PageTabs
        label="People sections"
        tabs={tabs}
        current={current}
        actions={
          canAdd ? (
            <Button asChild>
              <Link href={routes.admin_add_user()}>
                Add user
                <UserPlus aria-hidden />
              </Link>
            </Button>
          ) : null
        }
      />
    </header>
  );
}

/** Breadcrumbs shared by the People tabs, so every tab reads as one place. */
export function peopleLayoutContext(title: string) {
  return {
    title,
    breadcrumbs: [
      { label: "Dashboard", href: routes.dashboard() },
      { label: "People", href: routes.admin_people() },
      { label: title },
    ],
  };
}
