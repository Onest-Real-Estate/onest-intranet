import { Link } from "@inertiajs/react";
import { ArrowRight } from "lucide-react";

import { DataTable, type DataTableColumn } from "@/components/design-system/data-table";
import { StatusBadge } from "@/components/design-system/status-badge";
import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system/surface-card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { routes } from "@/lib/routes";
import { presentStatus, TRANSACTION_STATUS } from "@/lib/status";
import type { DashboardTransaction } from "@/types";

const columns: DataTableColumn<DashboardTransaction>[] = [
  {
    id: "property",
    header: "Property",
    cell: (row) => (
      <div className="flex min-w-64 items-center gap-3">
        <img
          src={row.imageUrl}
          alt=""
          width={40}
          height={40}
          className="size-10 rounded-md object-cover"
        />
        <span className="min-w-0">
          <span className="block max-w-80 truncate font-medium">{row.address}</span>
          <span className="text-muted-foreground mt-0.5 block text-xs">
            {row.type} · {row.stage}
          </span>
        </span>
      </div>
    ),
  },
  {
    id: "closing",
    header: "Closing",
    cell: (row) => row.closing,
    className: "text-muted-foreground",
  },
  {
    id: "status",
    header: "Status",
    cell: (row) => (
      <StatusBadge status={presentStatus(row.status, TRANSACTION_STATUS)} />
    ),
  },
];

export function ActiveTransactions({
  transactions,
}: {
  transactions: DashboardTransaction[];
}) {
  return (
    <SurfaceCard className="arrive gap-4 pb-0">
      <PanelHeader
        title="Active transactions"
        description="Deals that need your attention next."
        action={
          <Button asChild variant="outline" size="sm">
            <Link href={routes.coming_soon("agent-transactions")}>
              Manage pipeline
              <ArrowRight className="size-4" aria-hidden />
            </Link>
          </Button>
        }
      />
      {/* `bare`: the card already draws the frame, so the table only needs its
          own rules. Full-bleed so rows read to the card edge. */}
      <SurfaceCardContent className="px-0">
        <DataTable
          frame="bare"
          rows={transactions}
          columns={columns}
          rowKey={(row) => row.id}
          caption="Active transaction pipeline"
          getRowLabel={(row) => row.address}
          emptyTitle="No active transactions"
          emptyDescription="New transactions will appear here once they enter your pipeline."
          className="border-t [&_td:first-child]:pl-5 [&_td:last-child]:pr-5 [&_th:first-child]:pl-5 [&_th:last-child]:pr-5 [&_tr:last-child]:border-0"
        />
      </SurfaceCardContent>
    </SurfaceCard>
  );
}

export function ActiveTransactionsSkeleton() {
  return (
    <SurfaceCard className="gap-4">
      <PanelHeader
        title="Active transactions"
        description="Deals that need your attention next."
      />
      <SurfaceCardContent className="grid gap-3">
        {["t1", "t2", "t3", "t4"].map((id) => (
          <Skeleton key={id} className="h-14 w-full" />
        ))}
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
