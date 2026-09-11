import { Link } from "@inertiajs/react";
import type { LucideIcon } from "lucide-react";
import { ArrowRight, ChevronRight, ExternalLink, FileText, Link2 } from "lucide-react";

import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
  SurfaceCardMeta,
} from "@/components/design-system/surface-card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { DashboardDocuments } from "@/types";

const KIND_ICONS: Record<string, LucideIcon> = {
  file: FileText,
  link: Link2,
};

/**
 * Shortcuts into the reader's office resource library.
 *
 * The rows used to be placeholder names that all pointed at the same
 * coming-soon page. They are now the files and links published for this
 * reader's office chain, and each one goes where it actually lives: a file
 * through the protected download view that re-checks scope on every hit, a
 * link straight out to its destination.
 */
export function QuickDocuments({ documents }: { documents: DashboardDocuments }) {
  const truncated = documents.total > documents.items.length;
  return (
    <SurfaceCard className="arrive">
      <PanelHeader
        title="Quick documents"
        meta={
          truncated ? (
            <SurfaceCardMeta>
              {documents.items.length} of {documents.total}
            </SurfaceCardMeta>
          ) : undefined
        }
        action={
          <Button asChild variant="ghost" size="sm" className="gap-1">
            <Link href={documents.viewAllHref}>
              View all
              <ArrowRight className="size-3.5" strokeWidth={1.5} aria-hidden />
            </Link>
          </Button>
        }
      />
      <SurfaceCardContent className="px-2">
        <ul className="grid">
          {documents.items.map((doc) => {
            const Icon = KIND_ICONS[doc.kind] ?? FileText;
            const external = doc.kind === "link";
            const rowClass =
              "hover:bg-muted/50 focus-visible:ring-ring focus-visible:ring-offset-background group flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm transition-colors duration-(--motion-fast) focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none";
            const body = (
              <>
                <Icon
                  className="text-muted-foreground group-hover:text-foreground size-4 shrink-0 transition-colors duration-(--motion-fast)"
                  strokeWidth={1.5}
                  aria-hidden
                />
                <span className="min-w-0 flex-1 truncate">{doc.name}</span>
                {external ? (
                  <ExternalLink
                    className="text-muted-foreground/60 size-4 shrink-0"
                    strokeWidth={1.5}
                    aria-hidden
                  />
                ) : (
                  <ChevronRight
                    className="text-muted-foreground/60 size-4 shrink-0"
                    strokeWidth={1.5}
                    aria-hidden
                  />
                )}
              </>
            );
            return (
              <li key={doc.id}>
                {/* A link resource points outside the hub, and a file download
                    is a plain HTTP response rather than an Inertia visit, so
                    neither is a client-side navigation. */}
                {external ? (
                  <a
                    href={doc.href}
                    target="_blank"
                    rel="noreferrer noopener"
                    className={rowClass}
                  >
                    {body}
                    <span className="sr-only">(opens in a new tab)</span>
                  </a>
                ) : (
                  <a href={doc.href} className={rowClass}>
                    {body}
                  </a>
                )}
              </li>
            );
          })}
        </ul>
      </SurfaceCardContent>
    </SurfaceCard>
  );
}

export function QuickDocumentsSkeleton() {
  return (
    <SurfaceCard>
      <PanelHeader title="Quick documents" />
      <SurfaceCardContent className="grid gap-2">
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
      </SurfaceCardContent>
    </SurfaceCard>
  );
}
