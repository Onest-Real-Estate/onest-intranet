import { ArrowRight, House } from "lucide-react";

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
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          <House className="size-5" strokeWidth={1.5} />
          Active transactions
        </CardTitle>
        <Button variant="link" size="sm" className="px-0">
          Manage pipeline
          <ArrowRight className="size-4" strokeWidth={1.5} />
        </Button>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
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
                      className="size-10 rounded-md object-cover"
                    />
                    <span className="font-medium whitespace-normal">{row.address}</span>
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
