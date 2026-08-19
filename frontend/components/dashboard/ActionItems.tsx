import { Clock, ListTodo } from "lucide-react";
import { useState } from "react";
import { IconWell } from "@/components/IconWell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import type { DashboardActionItems } from "@/types";

export function ActionItems({ data }: { data: DashboardActionItems }) {
  // Local only: there is no completion endpoint yet, but a checkbox that
  // snaps back the moment you tick it reads as broken rather than pending.
  const [done, setDone] = useState<Record<string, boolean>>({});
  const remaining = data.items.filter((item) => !done[item.id]).length;

  return (
    <Card className="arrive">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle asChild className="flex items-center gap-2">
          <h2>
            <IconWell
              icon={ListTodo}
              tone="muted"
              className="size-8"
              iconClassName="size-4"
            />
            Action items
          </h2>
        </CardTitle>
        <span className="bg-muted text-muted-foreground shrink-0 rounded-full px-2 py-0.5 text-xs tabular-nums">
          {remaining} of {data.total} open
        </span>
      </CardHeader>
      <CardContent className="grid gap-3">
        {data.items.map((item) => {
          const checked = Boolean(done[item.id]);
          return (
            <div
              key={item.id}
              className="flex items-start gap-3 rounded-lg border p-3 transition-opacity"
              data-done={checked || undefined}
            >
              <Checkbox
                className="mt-0.5"
                aria-label={item.title}
                checked={checked}
                onCheckedChange={(value) =>
                  setDone((prev) => ({ ...prev, [item.id]: value === true }))
                }
              />
              <span className={`grid min-w-0 gap-0.5 ${checked ? "opacity-60" : ""}`}>
                <span
                  className={`text-sm font-medium ${checked ? "line-through" : ""}`}
                >
                  {item.title}
                </span>
                <span className="text-muted-foreground text-xs">{item.property}</span>
                <span
                  className={
                    item.late && !checked
                      ? "text-destructive flex items-center gap-1.5 text-xs"
                      : "text-muted-foreground flex items-center gap-1.5 text-xs"
                  }
                >
                  <Clock className="size-3.5" strokeWidth={1.5} aria-hidden />
                  {item.late && !checked ? `Late · ${item.due}` : item.due}
                </span>
              </span>
            </div>
          );
        })}
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
