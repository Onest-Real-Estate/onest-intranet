import { Head, Link, router, usePage } from "@inertiajs/react";
import { ArrowRight, ClipboardList, Plus } from "lucide-react";
import { useState } from "react";

import {
  DataTable,
  type DataTableColumn,
  EmptyState,
  FilterControls,
  FilterField,
  PageHeader,
  Pagination,
  SearchControl,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
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
import { buildListUrl } from "@/lib/list-query";
import { routes } from "@/lib/routes";
import type { AdminTransactionsPageProps, TransactionListRow } from "@/types";

const ACCESS = { all: ["web.view_transactions"] };
const ALL = "__all__";

const STATUS_OPTIONS = [
  { value: "draft", label: "Draft" },
  { value: "preparing", label: "Preparing" },
  { value: "under_contract", label: "Under contract" },
  { value: "pending", label: "Pending" },
  { value: "compliance_review", label: "Compliance review" },
  { value: "ready_to_close", label: "Ready to close" },
  { value: "closed", label: "Closed" },
  { value: "on_hold", label: "On hold" },
  { value: "archived", label: "Archived" },
  { value: "cancelled", label: "Cancelled" },
];

const TYPE_OPTIONS = [
  { value: "buy", label: "Buy" },
  { value: "sell", label: "Sell" },
  { value: "rent", label: "Rent" },
];

const columns: DataTableColumn<TransactionListRow>[] = [
  {
    id: "reference",
    header: "Reference",
    cell: (row) => (
      <Link
        href={routes.transaction_workspace(row.publicId)}
        className="font-medium underline-offset-2 hover:underline"
      >
        {row.reference || "Untitled"}
      </Link>
    ),
  },
  {
    id: "property",
    header: "Property",
    cell: (row) => row.propertyLine || "—",
  },
  {
    id: "office",
    header: "Office",
    cell: (row) => row.office?.name || "—",
    className: "hidden @lg:table-cell",
    headerClassName: "hidden @lg:table-cell",
  },
  {
    id: "agent",
    header: "Primary agent",
    cell: (row) => row.primaryAgent?.displayName || "—",
    className: "hidden @xl:table-cell",
    headerClassName: "hidden @xl:table-cell",
  },
  {
    id: "status",
    header: "Status",
    cell: (row) => <StatusBadge status={{ label: row.statusLabel, tone: "info" }} />,
  },
  {
    id: "closing",
    header: "Closing",
    cell: (row) => row.closingDate || "—",
    className: "text-muted-foreground hidden @2xl:table-cell",
    headerClassName: "hidden @2xl:table-cell",
  },
];

export default function AdminTransactions() {
  const { items, capabilities } = usePage<AdminTransactionsPageProps>().props;
  const filters = items.filters;
  const [query, setQuery] = useState(filters.q || "");

  function visit(next: Record<string, string>, page?: number) {
    const merged = { ...filters, ...next };
    router.get(
      buildListUrl(routes.admin_transactions(), window.location.search, {
        q: next.q !== undefined ? next.q : query,
        page,
        filters: merged,
      }),
      {},
      { preserveState: true, preserveScroll: true, replace: true },
    );
  }

  return (
    <PermissionRequired permission={ACCESS}>
      <Head title="Transactions" />
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 py-6">
        <PageHeader
          title="Transactions"
          description="Scoped brokerage deals in your reach."
          actions={
            capabilities.create ? (
              <Button asChild>
                <Link href={routes.transaction_new()}>
                  <Plus className="size-4" aria-hidden />
                  New transaction
                </Link>
              </Button>
            ) : null
          }
        />

        <SurfaceCard>
          <SurfaceCardContent className="space-y-4 py-5">
            <FilterControls>
              <SearchControl
                value={query}
                onValueChange={setQuery}
                onSearch={(value) => visit({ q: value }, 1)}
                placeholder="Search reference, MLS, address…"
              />
              <FilterField label="Status" hideLabel>
                <Select
                  value={filters.status || ALL}
                  onValueChange={(next) =>
                    visit({ status: next === ALL ? "" : next }, 1)
                  }
                >
                  <SelectTrigger size="sm" aria-label="Status">
                    <SelectValue placeholder="Any status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ALL}>Any status</SelectItem>
                    {STATUS_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </FilterField>
              <FilterField label="Type" hideLabel>
                <Select
                  value={filters.transactionType || ALL}
                  onValueChange={(next) =>
                    visit({ transactionType: next === ALL ? "" : next }, 1)
                  }
                >
                  <SelectTrigger size="sm" aria-label="Type">
                    <SelectValue placeholder="Any type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ALL}>Any type</SelectItem>
                    {TYPE_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </FilterField>
            </FilterControls>

            {items.items.length === 0 ? (
              <EmptyState
                icon={ClipboardList}
                title="No transactions in scope"
                description="Nothing matches these filters in your office reach."
                actions={
                  capabilities.create ? (
                    <Button asChild>
                      <Link href={routes.transaction_new()}>
                        New transaction
                        <ArrowRight className="size-4" aria-hidden />
                      </Link>
                    </Button>
                  ) : null
                }
              />
            ) : (
              <>
                <DataTable
                  caption="Transactions"
                  columns={columns}
                  rows={items.items}
                  rowKey={(row) => row.publicId}
                  emptyTitle="No transactions"
                  emptyDescription="Nothing matches these filters."
                />
                <Pagination
                  pagination={items.pagination}
                  onPageChange={(page) => visit({}, page)}
                />
              </>
            )}
          </SurfaceCardContent>
        </SurfaceCard>
      </div>
    </PermissionRequired>
  );
}

AdminTransactions.layout = (page: React.ReactNode) => <HubLayout>{page}</HubLayout>;
