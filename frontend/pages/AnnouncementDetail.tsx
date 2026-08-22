import { Head, Link, usePage } from "@inertiajs/react";
import { ArrowLeft, Download } from "lucide-react";

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
            {announcement.hasAttachment ? (
              <div className="mt-5">
                <Button variant="outline" size="sm" asChild>
                  {/* Plain anchor: an Inertia visit would XHR the bytes rather
                      than hand them to the browser's download flow. The URL is
                      re-authorized server-side on every request. */}
                  <a href={routes.announcement_attachment(announcement.id)} download>
                    <Download className="size-3.5 shrink-0" aria-hidden />
                    <span className="max-w-64 truncate">
                      {announcement.attachmentName
                        ? `Download (${announcement.attachmentName})`
                        : "Download attachment"}
                    </span>
                  </a>
                </Button>
              </div>
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
