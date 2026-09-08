import { Head, Link, router, usePage } from "@inertiajs/react";
import {
  BadgeCheck,
  Building2,
  CalendarClock,
  CircleUser,
  FileText,
  Plus,
} from "lucide-react";
import { useState } from "react";
import {
  DataTable,
  FormErrorSummary,
  PageHeader,
  SearchControl,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
  toStatusTone,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { routes } from "@/lib/routes";
import type { AgentContractAdministrationPageProps } from "@/types";

const ACCESS = { all: ["web.view_agent_contracts"] };
const ALL = "__all__";

export default function AgentContractAdministration() {
  const { contracts, capabilities, statusOptions, errors } =
    usePage<AgentContractAdministrationPageProps>().props;
  const [query, setQuery] = useState(contracts.filters.q ?? "");

  function visit(patch: Record<string, string>) {
    router.get(
      routes.admin_agent_contracts(),
      {
        q: query,
        status: contracts.filters.status,
        ...patch,
      },
      { preserveScroll: true, preserveState: true, replace: true },
    );
  }

  return (
    <PermissionRequired permission={ACCESS}>
      <div className="grid gap-8">
        <Head title="Agent Contracts" />
        <PageHeader
          title="Agent Contracts"
          description="Assemble, validate, preview, and issue brokerage agreements for agents in your scope."
          actions={
            capabilities.canManage ? (
              <Button asChild>
                <Link href={routes.agent_contract_new()}>
                  <Plus className="size-4" aria-hidden />
                  New contract
                </Link>
              </Button>
            ) : null
          }
        />
        <FormErrorSummary errors={errors} />

        <SurfaceCard>
          <SurfaceCardContent className="grid gap-4">
            <div className="flex flex-wrap items-end gap-4">
              <SearchControl
                label="Search contracts"
                value={query}
                onValueChange={setQuery}
                onSearch={(next) => visit({ q: next })}
                onClear={() => {
                  setQuery("");
                  visit({ q: "" });
                }}
                placeholder="Agent or contract id"
                className="max-w-xl"
              />
              <Select
                value={contracts.filters.status || ALL}
                onValueChange={(next) => visit({ status: next === ALL ? "" : next })}
              >
                <SelectTrigger className="w-48" aria-label="Status filter">
                  <SelectValue placeholder="Any status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>Any status</SelectItem>
                  {statusOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <DataTable
              frame="bleed"
              caption="Agent contracts"
              rows={contracts.items}
              rowKey={(row) => row.publicId}
              emptyTitle="No contracts yet"
              emptyDescription="Create a draft for an in-scope agent to get started."
              columns={[
                {
                  id: "agent",
                  header: "Agent",
                  icon: CircleUser,
                  cell: (row) => (
                    <div className="grid gap-0.5">
                      <span className="font-semibold">{row.recipientName}</span>
                      <span className="text-muted-foreground text-xs">
                        {row.recipientEmail}
                      </span>
                    </div>
                  ),
                },
                {
                  id: "office",
                  header: "Office",
                  icon: Building2,
                  cell: (row) => <span className="text-sm">{row.officeName}</span>,
                },
                {
                  id: "status",
                  header: "Status",
                  icon: BadgeCheck,
                  cell: (row) => (
                    <StatusBadge
                      status={{
                        label: row.statusLabel,
                        tone: toStatusTone(row.statusTone),
                      }}
                    />
                  ),
                },
                {
                  id: "effective",
                  header: "Effective",
                  icon: CalendarClock,
                  cell: (row) => <span className="text-sm">{row.effectiveOn}</span>,
                },
                {
                  id: "template",
                  header: "Template",
                  icon: FileText,
                  cell: (row) => (
                    <span className="text-sm">{row.templateLabel || "—"}</span>
                  ),
                },
                {
                  id: "actions",
                  header: <span className="sr-only">Actions</span>,
                  cell: (row) => (
                    <Button asChild variant="outline" size="sm">
                      <Link href={routes.agent_contract_workspace(row.publicId)}>
                        Open
                      </Link>
                    </Button>
                  ),
                },
              ]}
            />
          </SurfaceCardContent>
        </SurfaceCard>
      </div>
    </PermissionRequired>
  );
}

AgentContractAdministration.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Agent Contracts",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Agent Contracts", href: routes.admin_agent_contracts() },
        ],
      },
      variant: "standard",
    },
  ] as const;
