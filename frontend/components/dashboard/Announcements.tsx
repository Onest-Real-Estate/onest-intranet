import { Link } from "@inertiajs/react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";

import { SurfaceCard } from "@/components/design-system/surface-card";
import { cn } from "@/lib/utils";
import type { DashboardAnnouncement, DashboardAnnouncements } from "@/types";

function Slide({
  announcement,
  position,
  total,
  current,
  media,
}: {
  announcement: DashboardAnnouncement;
  position: number;
  total: number;
  current: boolean;
  /**
   * At least one story in this band carries artwork, so every frame keeps the
   * media proportion and the track stays one height. With no artwork anywhere,
   * the band is type — and a 16:8 frame would be four hundred pixels of empty
   * ground held open for a photograph nobody uploaded.
   */
  media: boolean;
}) {
  const hasArtwork = Boolean(announcement.imageUrl);

  return (
    <article
      // `article` carries its own role, so the APG's `role="group"` would be an
      // invalid override; the role description is what makes a screen reader
      // announce this as a slide. The slides that are off-frame are hidden from
      // assistive technology rather than read as part of the page.
      aria-roledescription="slide"
      aria-label={`${position} of ${total}: ${announcement.title}`}
      aria-hidden={current ? undefined : true}
      className="h-full w-full shrink-0"
    >
      {/*
        Copy sits directly on the photograph — no scrim, no gradient, no panel
        behind it, so the image is shown exactly as uploaded. Legibility comes
        from `on-media-ink`: a fixed light ink with a shadow on the glyphs
        themselves rather than a wash over the picture.

        That is a weaker guarantee than a scrim, and deliberately so. It holds
        because the artwork is decorative and the same headline, summary, and
        category are available as ordinary text on the announcements feed and
        the detail page — nothing here is the only copy of anything.

        With no artwork there is nothing to lay copy *over*, and the two things
        that were tried in its place both failed: light media ink on the pale
        gold well reached about 1.3:1, and a photograph-shaped frame with no
        photograph in it held four hundred pixels of empty ground open. So a
        story without artwork is not treated as media at all. It is a typographic
        slide on the card's own surface, set in the page's own ink and centred in
        whatever height the band ends up with, which is the form the words
        deserved in the first place.
      */}
      <div
        className={cn(
          "relative h-full w-full overflow-hidden",
          media
            ? "bg-muted aspect-[4/3] sm:aspect-[16/8]"
            : "bg-card min-h-52 sm:min-h-56",
        )}
      >
        {hasArtwork ? (
          <img
            src={announcement.imageUrl ?? undefined}
            // Decorative: the headline over it already names the story.
            alt=""
            loading="lazy"
            className="size-full object-cover"
          />
        ) : null}
        <div
          className={cn(
            "grid gap-1.5",
            hasArtwork
              ? "on-media-ink absolute inset-x-0 bottom-0 px-5 pb-5 sm:px-6 sm:pb-6"
              : "text-foreground h-full content-center px-5 py-7 sm:px-8 sm:py-9",
          )}
        >
          <p
            className={cn(
              "text-xs font-bold tracking-[0.08em] uppercase",
              hasArtwork ? undefined : "text-muted-foreground",
            )}
          >
            {announcement.tag}
          </p>
          <h3 className="line-clamp-2 text-xl leading-snug font-bold tracking-[-0.02em] text-balance sm:text-2xl">
            {/* Only the current slide is reachable: the off-frame ones are
                hidden from assistive technology and must not take focus. */}
            <Link
              href={announcement.href}
              tabIndex={current ? undefined : -1}
              className={cn(
                "rounded-sm hover:underline focus-visible:ring-2 focus-visible:outline-none",
                hasArtwork ? "focus-visible:ring-on-media" : "focus-visible:ring-ring",
              )}
            >
              {announcement.title}
            </Link>
          </h3>
          {announcement.excerpt ? (
            <p
              className={cn(
                "line-clamp-2 max-w-2xl text-sm leading-6",
                hasArtwork ? undefined : "text-muted-foreground",
              )}
            >
              {announcement.excerpt}
            </p>
          ) : null}
          {announcement.publisher ? (
            <p
              className={cn(
                "text-xs font-medium",
                hasArtwork ? "opacity-90" : "text-muted-foreground",
              )}
            >
              Via {announcement.publisher}
            </p>
          ) : null}
        </div>
      </div>
    </article>
  );
}

/**
 * The brokerage's news: one story at a time, filling its whole card.
 *
 * Each story is one full-bleed hero — the photograph runs edge to edge, the
 * headline sits over it on a scrim built from the page's own background
 * tokens, and the controls float on the picture instead of in a header bar —
 * so the band spends every pixel of its height on the story itself.
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
  const media = items.some((item) => Boolean(item.imageUrl));

  function show(index: number) {
    setCurrent(Math.min(Math.max(index, 0), items.length - 1));
  }

  return (
    <SurfaceCard className="h-full gap-0 py-0">
      {/*
        A named `section` is a `region`, which the APG lists alongside `group`
        for a carousel — and unlike an explicit `role="group"` it is the
        element's own semantics rather than an override. The heading is real
        for document outline but visual chrome is the story itself.
      */}
      <section
        aria-roledescription="carousel"
        aria-label="News and announcements"
        className="group/carousel relative h-full overflow-hidden rounded-(--radius-card)"
      >
        <h2 className="sr-only">News & announcements</h2>

        <div className="h-full overflow-hidden">
          <div
            className="motion-safe:duration-(--motion-slow) flex h-full transition-transform ease-out"
            style={{ transform: `translateX(-${current * 100}%)` }}
          >
            {items.map((item, index) => (
              <Slide
                key={item.id}
                announcement={item}
                position={index + 1}
                total={items.length}
                current={index === current}
                media={media}
              />
            ))}
          </div>
        </div>

        {!single ? (
          <>
            <span className="bg-background/85 absolute top-4 left-4 z-10 rounded-md border px-2.5 py-1 text-xs font-semibold tabular-nums backdrop-blur-sm">
              {current + 1} / {items.length}
            </span>
            <div className="absolute top-4 right-4 z-10 flex gap-1.5">
              <button
                type="button"
                aria-label="Previous announcement"
                disabled={current === 0}
                onClick={() => show(current - 1)}
                className="bg-background/85 hover:bg-background focus-visible:ring-ring grid size-9 place-items-center rounded-full border shadow-xs backdrop-blur-sm transition-colors duration-(--motion-fast) focus-visible:ring-2 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-40"
              >
                <ChevronLeft className="size-4" aria-hidden />
              </button>
              <button
                type="button"
                aria-label="Next announcement"
                disabled={current === items.length - 1}
                onClick={() => show(current + 1)}
                className="bg-background/85 hover:bg-background focus-visible:ring-ring grid size-9 place-items-center rounded-full border shadow-xs backdrop-blur-sm transition-colors duration-(--motion-fast) focus-visible:ring-2 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-40"
              >
                <ChevronRight className="size-4" aria-hidden />
              </button>
            </div>
            <div className="absolute inset-x-0 bottom-0 z-10 hidden justify-end gap-1.5 px-6 pb-3 sm:flex">
              {items.map((item, index) => (
                <button
                  key={item.id}
                  type="button"
                  aria-label={`Show announcement ${index + 1}`}
                  aria-current={index === current}
                  onClick={() => show(index)}
                  className="focus-visible:ring-ring group grid size-7 place-items-center rounded-full focus-visible:ring-2 focus-visible:outline-none"
                >
                  <span
                    className={cn(
                      "rounded-full transition-[width,background-color]",
                      // The inactive dot has to read on two different grounds:
                      // an unknown photograph, where a translucent white is the
                      // only safe mark, and the card's own white surface, where
                      // that same mark is invisible.
                      index === current
                        ? "bg-primary h-1.5 w-5"
                        : media
                          ? "bg-background/70 group-hover:bg-background h-1.5 w-1.5"
                          : "bg-border-strong group-hover:bg-muted-foreground h-1.5 w-1.5",
                    )}
                    aria-hidden
                  />
                </button>
              ))}
            </div>
          </>
        ) : null}
      </section>
    </SurfaceCard>
  );
}

export function AnnouncementsSkeleton() {
  return (
    <SurfaceCard state="loading" className="h-full gap-0 py-0">
      <div className="bg-muted animate-pulse aspect-[4/3] w-full sm:aspect-[16/8]" />
    </SurfaceCard>
  );
}
