import { Clock, ListTodo } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import type { DashboardActionItems } from "@/types";

export function ActionItems({ data }: { data: DashboardActionItems }) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          <ListTodo className="size-5" strokeWidth={1.5} />
          Action items
        </CardTitle>
        <span className="text-muted-foreground text-xs">{data.total} total</span>
      </CardHeader>
      <CardContent className="grid gap-3">
        {data.items.map((item) => (
          <div key={item.id} className="flex items-start gap-3 rounded-lg border p-3">
            <Checkbox className="mt-0.5" aria-label={item.title} />
            <span className="grid min-w-0 gap-0.5">
              <span className="text-sm font-medium">{item.title}</span>
              <span className="text-muted-foreground text-xs">{item.property}</span>
              <span
                className={
                  item.late
                    ? "text-destructive flex items-center gap-1.5 text-xs"
                    : "text-muted-foreground flex items-center gap-1.5 text-xs"
                }
              >
                <Clock className="size-3.5" strokeWidth={1.5} />
                {item.late ? `Late · ${item.due}` : item.due}
              </span>
            </span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export function ActionItemsSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-5 w-28" />
      </CardHeader>
      <CardContent className="grid gap-3">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </CardContent>
    </Card>
  );
}
