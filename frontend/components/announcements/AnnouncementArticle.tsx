import { Download, ExternalLink, Pin } from "lucide-react";
import { useState } from "react";
import { AnnouncementBody } from "@/components/announcements/AnnouncementBody";
import {
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { Button } from "@/components/ui/button";
import {
  audienceIcon,
  audienceSummary,
  categoryPresentation,
  formatBytes,
  heroSources,
  priorityPresentation,
} from "@/lib/announcements";
import type { AnnouncementDetail } from "@/types";

/**
 * One announcement, as a reader sees it.
 *
 * This is the *only* renderer for announcement content. The detail page mounts
 * it for a published notice; the administration workspace mounts the same
 * component over an unpublished draft's payload, which is what makes "preview
 * matches the user-facing rendering" a property of the code shape rather than
 * two templates somebody has to keep in step.
 *
 * It renders and nothing else. Authority was decided before the payload was
 * built — for a reader by the audience predicate, for an administrator by the
 * workspace's scope — so there is no visibility logic here to get wrong.
 */
export function AnnouncementArticle({
  announcement,
  headingLevel = "h2",
  showAudience = true,
}: {
  announcement: AnnouncementDetail;
  /** The heading used for the article's own sections, below the page title. */
  headingLevel?: "h2" | "h3";
  showAudience?: boolean;
}) {
  const hero = heroSources(announcement.hero);
  const [heroBroken, setHeroBroken] = useState(false);
  const SectionHeading = headingLevel;

  return (
    <div className="grid gap-6">
      {hero && !heroBroken ? (
        <img
          src={hero.src}
          srcSet={hero.srcSet}
          sizes="(min-width: 1024px) 60rem, 100vw"
          width={hero.width ?? undefined}
          height={hero.height ?? undefined}
          // Decorative: the headline already carries the meaning, so a
          // description here would be read out twice.
          alt=""
          // A hero that fails to load must not leave a broken-image icon in its
          // place; everything below stands on its own without it.
          onError={() => setHeroBroken(true)}
          className="bg-muted max-h-96 w-full rounded-xl border object-cover"
        />
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={priorityPresentation(announcement.priority)} />
        <StatusBadge status={categoryPresentation(announcement.category)} />
        {announcement.isPinned ? (
          <span className="text-muted-foreground flex items-center gap-1 text-xs font-medium">
            <Pin className="size-3.5" aria-hidden />
            Pinned to the top of the feed
          </span>
        ) : null}
      </div>
      <p className="sr-only">
        {announcement.priority.srLabel}. {announcement.category.srLabel}.
      </p>

      <SurfaceCard>
        <SurfaceCardContent>
          {/* The block tree, never the raw source: see AnnouncementBody. A
              long notice simply flows — no clamp, no "read more", because an
              announcement that has been truncated has not been announced. */}
          <AnnouncementBody blocks={announcement.bodyBlocks} />

          {announcement.cta ? (
            <div className="mt-6">
              <Button asChild>
                {/* Plain anchor: the destination is outside the hub, so an
                    Inertia visit would try to render another app's HTML. */}
                <a
                  href={announcement.cta.url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {announcement.cta.label}
                  <ExternalLink className="size-3.5 shrink-0" aria-hidden />
                  <span className="sr-only">(opens in a new tab)</span>
                </a>
              </Button>
            </div>
          ) : null}

          {announcement.attachments.length > 0 ? (
            <section aria-labelledby="files-heading" className="mt-6 grid gap-2">
              <SectionHeading id="files-heading" className="text-sm font-semibold">
                Files
              </SectionHeading>
              <ul className="grid gap-2">
                {announcement.attachments.map((file) => (
                  <li key={file.id}>
                    <Button variant="outline" size="sm" asChild>
                      {/* Plain anchor: an Inertia visit would XHR the bytes
                          rather than hand them to the browser's download flow.
                          The path re-authorizes on every request. */}
                      <a href={file.url} download>
                        <Download className="size-3.5 shrink-0" aria-hidden />
                        <span className="max-w-64 truncate">{file.displayName}</span>
                        <span className="text-muted-foreground text-xs">
                          {formatBytes(file.byteSize)}
                        </span>
                      </a>
                    </Button>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </SurfaceCardContent>
      </SurfaceCard>

      {showAudience ? (
        <section aria-labelledby="audience-heading" className="grid gap-3">
          <SectionHeading id="audience-heading" className="text-sm font-semibold">
            Who this was sent to
          </SectionHeading>
          <p className="text-muted-foreground text-sm">
            {audienceSummary(announcement.audience)}
          </p>
          <ul className="flex flex-wrap gap-2">
            {announcement.audience.map((entry) => {
              const Icon = audienceIcon(entry.kind);
              return (
                <li
                  key={`${entry.kind}-${entry.code}-${entry.officeId ?? entry.userId ?? "all"}`}
                  className="bg-muted text-muted-foreground flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs"
                >
                  <Icon className="size-3.5 shrink-0" aria-hidden />
                  {entry.label}
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
