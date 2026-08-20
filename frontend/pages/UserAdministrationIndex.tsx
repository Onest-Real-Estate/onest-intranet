import { Head, router, usePage } from "@inertiajs/react";
import { ArrowRight, Users } from "lucide-react";
import { useState } from "react";

import {
  DataTable,
  PageHeader,
  Pagination,
  PanelHeader,
  SearchControl,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { routes } from "@/lib/routes";
import type { UserAdministrationIndexPageProps } from "@/types";

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

/**
 * Find a user to administer.
 *
 * Deliberately thin — a search box and a list, and nothing that belongs to
 * full user management. Every row here already passed the server's scope
 * filter; the page never asks for a wider set and could not receive one.
 */
export default function UserAdministrationIndex() {
  const { users, statusOptions } = usePage<UserAdministrationIndexPageProps>().props;
  const [query, setQuery] = useState(users.filters.q ?? "");

  function visit(next: { q?: string; page?: number }) {
    router.get(
      routes.user_administration_index(),
      { q: next.q ?? query, page: next.page ?? 1 },
      { preserveState: true, replace: true },
    );
  }

  return (
    <div className="grid gap-10">
      <Head title="User administration" />
      <PageHeader
        title="User administration"
        description="Manage office placement, brokerage status, credentials, and role access for people in your scope."
      />

      <SurfaceCard>
        <PanelHeader
          divided
          title="People in your scope"
          description="Search by name, work email, or agent ID."
          meta={
            <span className="text-muted-foreground text-xs font-medium tabular-nums">
              {users.pagination.totalItems}{" "}
              {users.pagination.totalItems === 1 ? "person" : "people"}
            </span>
          }
        />
        <SurfaceCardContent className="grid gap-4">
          <SearchControl
            label="Search people"
            value={query}
            onValueChange={setQuery}
            onSearch={(next) => visit({ q: next })}
            onClear={() => visit({ q: "" })}
            placeholder="Name, email, or agent ID"
            className="max-w-xl"
          />
          <DataTable
            frame="bleed"
            caption="Users you may administer"
            rows={users.items}
            rowKey={(row) => String(row.id)}
            emptyTitle="Nobody matches"
            emptyDescription="No user inside your office or region scope matches that search."
            columns={[
              {
                id: "name",
                header: "Name",
                cell: (row) => (
                  <div className="flex min-w-40 items-center gap-3 sm:min-w-56">
                    <Avatar className="ring-border size-9 ring-1">
                      <AvatarFallback className="bg-secondary text-secondary-foreground text-xs font-semibold">
                        {initials(row.name)}
                      </AvatarFallback>
                    </Avatar>
                    <div className="grid min-w-0 gap-0.5">
                      <span className="truncate font-semibold">{row.name}</span>
                      <span className="text-muted-foreground truncate text-xs">
                        {row.email}
                      </span>
                    </div>
                  </div>
                ),
              },
              {
                id: "office",
                header: "Office",
                cell: (row) => row.officeName ?? "—",
                className: "hidden md:table-cell",
                headerClassName: "hidden md:table-cell",
              },
              {
                id: "status",
                header: "Status",
                cell: (row) => {
                  const status = statusOptions.find(
                    (option) => option.value === row.agentStatus,
                  );
                  return (
                    <StatusBadge
                      status={{
                        label: status?.label ?? row.agentStatus,
                        tone: status?.tone ?? "neutral",
                      }}
                    />
                  );
                },
                className: "hidden sm:table-cell",
                headerClassName: "hidden sm:table-cell",
              },
              {
                id: "identifier",
                header: "Agent ID",
                cell: (row) => row.agentIdentifier || "—",
                className: "hidden lg:table-cell",
                headerClassName: "hidden lg:table-cell",
              },
              {
                id: "actions",
                header: <span className="sr-only">Actions</span>,
                cell: (row) => (
                  <Button
                    variant="outline"
                    size="sm"
                    asChild
                    className="ml-auto size-8 px-0 sm:h-8 sm:w-auto sm:px-3"
                  >
                    <a href={routes.user_administration(row.id)}>
                      <span className="sr-only">Administer {row.name}</span>
                      <span className="hidden sm:inline" aria-hidden>
                        Administer
                      </span>
                      <ArrowRight className="size-3.5" aria-hidden />
                    </a>
                  </Button>
                ),
                className: "text-right",
                headerClassName: "text-right",
              },
            ]}
          />
          <Pagination
            pagination={users.pagination}
            onPageChange={(page) => visit({ page })}
          />
        </SurfaceCardContent>
      </SurfaceCard>

      {users.pagination.totalItems === 0 && !query ? (
        <SurfaceCard state="read-only">
          <SurfaceCardContent>
            <p className="text-muted-foreground flex items-center gap-2 text-sm">
              <Users className="size-4" aria-hidden />
              Your role does not scope you to anybody yet.
            </p>
          </SurfaceCardContent>
        </SurfaceCard>
      ) : null}
    </div>
  );
}

UserAdministrationIndex.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "User administration",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "User administration", href: routes.user_administration_index() },
        ],
      },
      variant: "standard",
    },
  ] as const;
