import { Calendar, Megaphone, Newspaper, TrendingUp } from "lucide-react";
import { IconWell } from "@/components/IconWell";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { DashboardAnnouncements } from "@/types";

function tagIcon(tag: string) {
  const key = tag.toLowerCase();
  if (key.includes("market")) {
    return TrendingUp;
  }
  if (key.includes("event") || key.includes("training")) {
    return Calendar;
  }
  if (key.includes("company") || key.includes("news")) {
    return Newspaper;
  }
  return Megaphone;
}

function TagBadge({ tag, variant }: { tag: string; variant: "secondary" | "outline" }) {
  const Icon = tagIcon(tag);
  return (
    <Badge variant={variant} className="rounded-full">
      <Icon className="size-3" strokeWidth={1.5} />
      {tag}
    </Badge>
  );
}

export function Announcements({ data }: { data: DashboardAnnouncements }) {
  return (
    <Card className="arrive">
      <CardHeader>
        {/* No news archive exists yet, so there is no "View all" to offer. */}
        <CardTitle asChild className="flex items-center gap-2">
          <h2>
            <IconWell
              icon={Newspaper}
              tone="muted"
              className="size-8"
              iconClassName="size-4"
            />
            News &amp; announcements
          </h2>
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 lg:grid-cols-2">
        <article className="grid gap-3">
          <img
            src={data.featured.imageUrl}
            alt=""
            className="h-40 w-full rounded-lg object-cover"
          />
          <TagBadge tag={data.featured.tag} variant="secondary" />
          <h3 className="leading-snug font-semibold">{data.featured.title}</h3>
          <p className="text-muted-foreground text-sm">{data.featured.excerpt}</p>
        </article>
        <ul className="grid gap-4">
          {data.items.map((item) => (
            <li
              key={item.title}
              className="grid gap-1 border-b pb-4 last:border-0 last:pb-0"
            >
              <TagBadge tag={item.tag} variant="outline" />
              <h3 className="font-medium leading-snug">{item.title}</h3>
              <p className="text-muted-foreground text-sm">{item.excerpt}</p>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

export function AnnouncementsSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-5 w-48" />
      </CardHeader>
      <CardContent className="grid gap-4 lg:grid-cols-2">
        <div className="grid gap-3">
          <Skeleton className="h-40 w-full rounded-lg" />
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-5 w-full" />
        </div>
        <div className="grid gap-4">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      </CardContent>
    </Card>
  );
}
