import { Link } from "@inertiajs/react";
import type { LucideIcon } from "lucide-react";
import { BookOpen, FilePenLine, FileText, FolderOpen } from "lucide-react";

import { IconWell } from "@/components/IconWell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
    <Card className="arrive">
      <CardHeader>
        <CardTitle asChild className="flex items-center gap-2">
          <h2>
            <IconWell
              icon={FolderOpen}
              tone="muted"
              className="size-8"
              iconClassName="size-4"
            />
            Quick documents
          </h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="grid gap-2">
          {documents.map((doc) => {
            const Icon = DOC_ICONS[doc.id] ?? FileText;
            return (
              <li key={doc.id}>
                {/* Until the document store exists, these lead to the section
                    that will hold them rather than to nothing at all. */}
                <Link
                  href={routes.coming_soon("documents-forms")}
                  className="hover:bg-muted/50 focus-visible:ring-ring focus-visible:ring-offset-background group flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm transition-colors focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
                >
                  <Icon
                    className="text-muted-foreground group-hover:text-foreground size-4 transition-colors"
                    strokeWidth={1.5}
                    aria-hidden
                  />
                  {doc.name}
                </Link>
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}

export function QuickDocumentsSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-5 w-36" />
      </CardHeader>
      <CardContent className="grid gap-2">
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
      </CardContent>
    </Card>
  );
}
