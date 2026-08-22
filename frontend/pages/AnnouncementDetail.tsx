import { Head, Link, usePage } from "@inertiajs/react";
import { ArrowLeft, Download } from "lucide-react";
import { useState } from "react";

import {
  PageHeader,
  StatusBadge,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { Button } from "@/components/ui/button";
import {
  audienceIcon,
  audienceSummary,
  categoryPresentation,
  formatBytes,
  heroSources,
  priorityPresentation,
} from "@/lib/announcements";
import { routes } from "@/lib/routes";
import type { AnnouncementDetailPageProps } from "@/types";

function formatPublished(value: string | null): string {
  if (!value) {
    return "Not yet published";
  }
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

/**
 * One announcement, reached by id.
 *
 * Arriving here at all means the server re-ran the audience predicate for this
 * reader on this request — the same one the feed used. The page shows who was
 * addressed, but it never decides: a reader who should not be here got a 403
 * before this component existed.
 */
export default function AnnouncementDetail() {
  const { announcement } = usePage<AnnouncementDetailPageProps>().props;
  const hero = heroSources(announcement.hero);
  const [heroBroken, setHeroBroken] = useState(false);

  return (
    <>
      <Head title={announcement.title} />
      <div className="grid gap-8">
        <PageHeader
          title={announcement.title}
          description={announcement.summary || undefined}
          meta={
            <span className="text-muted-foreground text-sm">
              Published {formatPublished(announcement.publishedAt)}
            </span>
          }
          actions={
            <Button variant="outline" size="sm" asChild>
              <Link href={routes.announcements()}>
                <ArrowLeft className="size-4" aria-hidden />
                All announcements
              </Link>
            </Button>
          }
        />

        {hero && !heroBroken ? (
          <img
            src={hero.src}
            srcSet={hero.srcSet}
            sizes="(min-width: 1024px) 60rem, 100vw"
            width={hero.width ?? undefined}
            height={hero.height ?? undefined}
            // Decorative: the headline above already carries the meaning, so a
            // description here would be read out twice.
            alt=""
            // A hero that fails to load must not leave a broken-image icon in
            // its place; the layout below stands on its own without it.
            onError={() => setHeroBroken(true)}
            className="bg-muted max-h-96 w-full rounded-xl border object-cover"
          />
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={priorityPresentation(announcement.priority)} />
          <StatusBadge status={categoryPresentation(announcement.category)} />
        </div>
        <p className="sr-only">
          {announcement.priority.srLabel}. {announcement.category.srLabel}.
        </p>

        <SurfaceCard>
          <SurfaceCardContent>
            <div className="text-sm leading-6 whitespace-pre-line">
              {announcement.body}
            </div>
            {announcement.attachments.length > 0 ? (
              <section aria-labelledby="files-heading" className="mt-6 grid gap-2">
                <h2 id="files-heading" className="text-sm font-semibold">
                  Files
                </h2>
                <ul className="grid gap-2">
                  {announcement.attachments.map((file) => (
                    <li key={file.id}>
                      <Button variant="outline" size="sm" asChild>
                        {/* Plain anchor: an Inertia visit would XHR the bytes
                            rather than hand them to the browser's download
                            flow. The path re-authorizes on every request. */}
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

        <section aria-labelledby="audience-heading" className="grid gap-3">
          <h2 id="audience-heading" className="text-sm font-semibold">
            Who this was sent to
          </h2>
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
      </div>
    </>
  );
}

AnnouncementDetail.layout = () =>
  [
    HubLayout,
    {
      context: {
        title: "Announcements",
        breadcrumbs: [
          { label: "Dashboard", href: routes.dashboard() },
          { label: "Announcements", href: routes.announcements() },
        ],
      },
    },
  ] as const;
