import { Link } from "@inertiajs/react";
import { CalendarDays, Clock, MapPin } from "lucide-react";

import { IconWell } from "@/components/IconWell";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { routes } from "@/lib/routes";
import type { DashboardSchedule } from "@/types";

export function MyDay({ schedule }: { schedule: DashboardSchedule }) {
  return (
    <Card className="arrive">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle asChild className="flex items-center gap-2">
          <h2>
            <IconWell
              icon={CalendarDays}
              tone="muted"
              className="size-8"
              iconClassName="size-4"
            />
            My day
          </h2>
        </CardTitle>
        <span className="bg-muted text-muted-foreground shrink-0 rounded-full px-2 py-0.5 text-xs">
          {schedule.dateLabel}
        </span>
      </CardHeader>
      <CardContent className="grid gap-4">
        {schedule.events.map((event) => (
          <div
            key={`${event.time}-${event.title}`}
            className="border-primary/40 grid gap-1 border-l-2 pl-3"
          >
            <p className="text-muted-foreground flex items-center gap-1.5 text-xs">
              <Clock className="size-3.5" strokeWidth={1.5} />
              {event.time}
            </p>
            <p className="text-sm font-medium">{event.title}</p>
            <p className="text-muted-foreground flex items-center gap-1.5 text-xs">
              <MapPin className="size-3.5" strokeWidth={1.5} />
              {event.place}
            </p>
          </div>
        ))}
      </CardContent>
      <CardFooter>
        <Button asChild variant="outline" size="sm" className="w-full">
          <Link href={routes.coming_soon("my-reservations")}>
            <CalendarDays className="size-4" strokeWidth={1.5} aria-hidden />
            View full calendar
          </Link>
        </Button>
      </CardFooter>
    </Card>
  );
}

export function MyDaySkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-5 w-24" />
      </CardHeader>
      <CardContent className="grid gap-4">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </CardContent>
    </Card>
  );
}
