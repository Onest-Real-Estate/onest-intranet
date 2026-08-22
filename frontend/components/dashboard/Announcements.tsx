import { Link } from "@inertiajs/react";
import { ChevronLeft, ChevronRight, Newspaper } from "lucide-react";
import { useState } from "react";

import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
  SurfaceCardMeta,
} from "@/components/design-system/surface-card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { DashboardAnnouncement, DashboardAnnouncements } from "@/types";

function Slide({
  announcement,
  position,
  total,
  current,
}: {
  announcement: DashboardAnnouncement;
  position: number;
  total: number;
  current: boolean;
}) {
  return (
    <article
      // `article` carries its own role, so the APG's `role="group"` would be an
      // invalid override; the role description is what makes a screen reader
      // announce this as a slide. The slides that are off-frame are hidden from
      // assistive technology rather than read as part of the page.
      aria-roledescription="slide"
      aria-label={`${position} of ${total}: ${announcement.title}`}
      aria-hidden={current ? undefined : true}
      className="w-full shrink-0 px-5"
    >
      <div className="bg-muted relative h-56 overflow-hidden rounded-xl border">
        {announcement.imageUrl ? (
          <img
            src={announcement.imageUrl}
            // Decorative: the headline over it already names the story.
            alt=""
            loading="lazy"
            className="size-full object-cover"
          />
        ) : (
          <span className="brand-well text-primary grid size-full place-items-center">
            <Newspaper className="size-8" aria-hidden />
          </span>
        )}
        {/*
          The scrim is the page's own background rather than black, so the
          overlay reads in both themes and the copy on it can stay on the
          ordinary foreground tokens — white text over an arbitrary photograph
          is a contrast bet we would lose eventually.
        */}
        <div className="from-background via-background/85 absolute inset-x-0 bottom-0 grid gap-1 bg-linear-to-t to-transparent px-4 pt-10 pb-4">
          <p className="text-muted-foreground text-xs font-semibold tracking-[0.08em] uppercase">
            {announcement.tag}
          </p>
          <h3 className="line-clamp-2 text-lg leading-snug font-semibold text-balance">
            {/* Only the current slide is reachable: the off-frame ones are
                hidden from assistive technology and must not take focus. */}
            <Link
              href={announcement.href}
              tabIndex={current ? undefined : -1}
              className="hover:text-primary focus-visible:ring-ring rounded-sm focus-visible:ring-2 focus-visible:outline-none"
            >
              {announcement.title}
            </Link>
          </h3>
          {announcement.excerpt ? (
            <p className="text-muted-foreground line-clamp-1 text-sm leading-5">
              {announcement.excerpt}
            </p>
          ) : null}
        </div>
      </div>
    </article>
  );
}

/**
 * The brokerage's news: one story at a time, at the top of every dashboard.
 *
 * Each story is one hero — the picture fills the frame and the headline sits
 * over it on a scrim — so the band spends its height on the photograph rather
 * than on a thumbnail and an equal measure of empty column beside it.
 *
 * The track is moved with a transform rather than by scrolling a snap
 * container. A programmatic scroll inside `scroll-snap-type: mandatory` is not
 * dependable: Chrome re-snaps to the slide it is already on the moment the
 * animation starts, and a profile with smooth scrolling switched off drops the
 * scroll entirely. A transform is one declarative property with one CSS
 * transition, and it behaves the same everywhere.
 *
 * It does not advance on its own. An auto-playing band would move the story
 * out from under someone mid-sentence, and the pause control that would make
 * that acceptable is more chrome than this earns.
 */
export function Announcements({ data }: { data: DashboardAnnouncements }) {
  const items = [data.featured, ...data.items];
  const [current, setCurrent] = useState(0);
  const single = items.length < 2;

  function show(index: number) {
    setCurrent(Math.min(Math.max(index, 0), items.length - 1));
  }

  return (
    <SurfaceCard className="arrive h-full">
      <PanelHeader
        title="News & announcements"
        meta={
          single ? undefined : (
            <SurfaceCardMeta>
              {current + 1} / {items.length}
            </SurfaceCardMeta>
          )
        }
        action={
          single ? undefined : (
            <div className="flex gap-1">
              <Button
                variant="outline"
                size="icon"
                aria-label="Previous announcement"
                disabled={current === 0}
                onClick={() => show(current - 1)}
              >
                <ChevronLeft aria-hidden />
              </Button>
              <Button
                variant="outline"
                size="icon"
                aria-label="Next announcement"
                disabled={current === items.length - 1}
                onClick={() => show(current + 1)}
              >
                <ChevronRight aria-hidden />
              </Button>
            </div>
          )
        }
      />
      <SurfaceCardContent className="grid gap-3 px-0">
        {/*
          A named `section` is a `region`, which the APG lists alongside `group`
          for a carousel — and unlike an explicit `role="group"` it is the
          element's own semantics rather than an override.
          The frame clips; the track inside it slides.
        */}
        <section
          aria-roledescription="carousel"
          aria-label="News and announcements"
          className="overflow-hidden"
        >
          <div
            className="motion-safe:duration-(--motion-slow) flex transition-transform ease-out"
            style={{ transform: `translateX(-${current * 100}%)` }}
          >
            {items.map((item, index) => (
              <Slide
                key={item.id}
                announcement={item}
                position={index + 1}
                total={items.length}
                current={index === current}
              />
            ))}
          </div>
        </section>
        {single ? null : (
          <div className="flex justify-center gap-1.5 px-5">
            {items.map((item, index) => (
              <button
                key={item.id}
                type="button"
                aria-label={`Show announcement ${index + 1}`}
                aria-current={index === current}
                onClick={() => show(index)}
                className="focus-visible:ring-ring group grid size-9 place-items-center rounded-md focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
              >
                <span
                  className={cn(
                    "h-1.5 rounded-full transition-[width,background-color]",
                    index === current
                      ? "bg-primary w-5"
                      : "bg-border group-hover:bg-primary/40 w-1.5",
                  )}
                  aria-hidden
                />
              </button>
            ))}
          </div>
        )}
      </SurfaceCardContent>
    </SurfaceCard>
  );
}

export function AnnouncementsSkeleton() {
  return (
    <SurfaceCard state="loading" className="h-full">
      <PanelHeader title="News & announcements" />
      <SurfaceCardContent className="px-0">
        <div className="px-5">
          <Skeleton className="h-56 w-full rounded-xl" />
        </div>
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
