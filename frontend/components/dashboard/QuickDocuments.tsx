import { Link } from "@inertiajs/react";
import type { LucideIcon } from "lucide-react";
import { BookOpen, ChevronRight, FilePenLine, FileText } from "lucide-react";

import {
  PanelHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system/surface-card";
import { Skeleton } from "@/components/ui/skeleton";
import { routes } from "@/lib/routes";
import type { DashboardDocument } from "@/types";

const DOC_ICONS: Record<string, LucideIcon> = {
  "doc-1": FilePenLine,
  "doc-2": BookOpen,
  "doc-3": FileText,
};

export function QuickDocuments({ documents }: { documents: DashboardDocument[] }) {
  return (
    <SurfaceCard className="arrive">
      <PanelHeader title="Quick documents" />
      <SurfaceCardContent className="px-2">
        <ul className="grid">
          {documents.map((doc) => {
            const Icon = DOC_ICONS[doc.id] ?? FileText;
            return (
              <li key={doc.id}>
                {/* Until the document store exists, these lead to the section
                    that will hold them rather than to nothing at all. */}
                <Link
                  href={routes.coming_soon("documents-forms")}
                  className="hover:bg-muted/50 focus-visible:ring-ring focus-visible:ring-offset-background group flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm transition-colors focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
                >
                  <Icon
                    className="text-muted-foreground group-hover:text-foreground size-4 shrink-0 transition-colors"
                    strokeWidth={1.5}
                    aria-hidden
                  />
                  <span className="min-w-0 flex-1 truncate">{doc.name}</span>
                  <ChevronRight
                    className="text-muted-foreground/60 size-4 shrink-0"
                    strokeWidth={1.5}
                    aria-hidden
                  />
                </Link>
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
