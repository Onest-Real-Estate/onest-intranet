import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system/surface-card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { DashboardAnnouncements } from "@/types";

/**
 * Categories are not statuses: they need to be readable, not colour-coded. A
 * quiet editorial eyebrow keeps the headline as the thing you actually scan.
 */
function Tag({ children, className }: { children: string; className?: string }) {
  return (
    <p
      className={cn(
        "text-muted-foreground text-[0.6875rem] font-semibold tracking-[0.08em] uppercase",
        className,
      )}
    >
      {children}
    </p>
  );
}

export function Announcements({ data }: { data: DashboardAnnouncements }) {
  return (
    <SurfaceCard className="arrive">
      {/* No news archive exists yet, so there is no "View all" to offer. */}
      <PanelHeader title="News & announcements" />
      <SurfaceCardContent className="grid gap-6 lg:grid-cols-2">
        <article className="grid content-start gap-2">
          {data.featured.imageUrl ? (
            <img
              src={data.featured.imageUrl}
              alt=""
              className="mb-1 h-44 w-full rounded-lg object-cover"
            />
          ) : null}
          <Tag>{data.featured.tag}</Tag>
          <h3 className="leading-snug font-semibold">{data.featured.title}</h3>
          <p className="text-muted-foreground text-sm leading-6">
            {data.featured.excerpt}
          </p>
        </article>
        <ul className="grid content-start gap-4">
          {data.items.map((item) => (
            <li
              key={item.title}
              className="grid gap-1.5 border-b pb-4 last:border-0 last:pb-0"
            >
              <Tag>{item.tag}</Tag>
              <h3 className="leading-snug font-medium">{item.title}</h3>
              <p className="text-muted-foreground text-sm leading-6">{item.excerpt}</p>
            </li>
          ))}
        </ul>
      </SurfaceCardContent>
    </SurfaceCard>
  );
}

export function AnnouncementsSkeleton() {
  return (
    <SurfaceCard>
      <PanelHeader title="News & announcements" />
      <SurfaceCardContent className="grid gap-6 lg:grid-cols-2">
        <div className="grid gap-3">
          <Skeleton className="h-44 w-full rounded-lg" />
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-5 w-full" />
        </div>
        <div className="grid gap-4">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
