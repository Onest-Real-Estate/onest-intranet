import { Link } from "@inertiajs/react";
import { ArrowRight, House } from "lucide-react";
import { IconWell } from "@/components/IconWell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { routes } from "@/lib/routes";
import type { DashboardTransaction } from "@/types";

function statusBadge(status: DashboardTransaction["status"]) {
  if (status === "action_needed") {
    return <Badge variant="warning">Action needed</Badge>;
  }
  return <Badge variant="success">On track</Badge>;
}

export function ActiveTransactions({
  transactions,
}: {
  transactions: DashboardTransaction[];
}) {
  return (
    <Card className="arrive">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle asChild className="flex items-center gap-2">
          <h2>
            <IconWell
              icon={House}
              tone="muted"
              className="size-8"
              iconClassName="size-4"
            />
            Active transactions
          </h2>
        </CardTitle>
        <Button asChild variant="link" size="sm" className="px-0">
          <Link href={routes.coming_soon("agent-transactions")}>
            Manage pipeline
            <ArrowRight className="size-4" strokeWidth={1.5} aria-hidden />
          </Link>
        </Button>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow className="[&>th]:tracking-[0.06em] [&>th]:uppercase">
              <TableHead>Property</TableHead>
              <TableHead className="hidden sm:table-cell">Type</TableHead>
              <TableHead className="hidden md:table-cell">Stage</TableHead>
              <TableHead className="hidden lg:table-cell">Closing</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {transactions.map((row) => (
              <TableRow key={row.id}>
                <TableCell>
                  <div className="flex items-center gap-3">
                    <img
                      src={row.imageUrl}
                      alt=""
                      width={40}
                      height={40}
                      className="size-10 rounded-md object-cover"
                    />
                    <span className="min-w-0">
                      <span className="block font-medium whitespace-normal">
                        {row.address}
                      </span>
                      {/* What the hidden columns carried, folded into the one
                          column small screens keep. */}
                      <span className="text-muted-foreground block text-xs whitespace-normal md:hidden">
                        {row.type} · {row.stage} · closes {row.closing}
                      </span>
                    </span>
                  </div>
                </TableCell>
                <TableCell className="hidden sm:table-cell">
                  <Badge variant="secondary">{row.type}</Badge>
                </TableCell>
                <TableCell className="text-muted-foreground hidden md:table-cell">
                  {row.stage}
                </TableCell>
                <TableCell className="hidden lg:table-cell">{row.closing}</TableCell>
                <TableCell>{statusBadge(row.status)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

export function ActiveTransactionsSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-5 w-48" />
      </CardHeader>
      <CardContent className="grid gap-3">
        {["t1", "t2", "t3", "t4"].map((id) => (
          <Skeleton key={id} className="h-12 w-full" />
        ))}
      </CardContent>
    </Card>
  );
}
