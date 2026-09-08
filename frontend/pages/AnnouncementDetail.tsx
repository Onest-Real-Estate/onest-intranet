import { Head, Link, usePage } from "@inertiajs/react";
import { ArrowLeft } from "lucide-react";
import { AnnouncementArticle } from "@/components/announcements/AnnouncementArticle";
import { PageHeader } from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { Button } from "@/components/ui/button";
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
 *
 * The body itself is drawn by `AnnouncementArticle`, which the administration
 * workspace also mounts for its preview, so what an author checks before
 * publishing is literally what a reader gets afterwards.
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
        <AnnouncementArticle announcement={announcement} />
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
