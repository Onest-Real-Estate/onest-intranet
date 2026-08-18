import type { LucideIcon } from "lucide-react";
import { BookOpen, FilePenLine, FileText, FolderOpen } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { DashboardDocument } from "@/types";

const DOC_ICONS: Record<string, LucideIcon> = {
  "doc-1": FilePenLine,
  "doc-2": BookOpen,
  "doc-3": FileText,
};

export function QuickDocuments({ documents }: { documents: DashboardDocument[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FolderOpen className="size-5" strokeWidth={1.5} />
          Quick documents
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="grid gap-2">
          {documents.map((doc) => {
            const Icon = DOC_ICONS[doc.id] ?? FileText;
            return (
              <li key={doc.id}>
                <button
                  type="button"
                  className="hover:bg-muted/50 flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm"
                >
                  <Icon className="text-muted-foreground size-4" strokeWidth={1.5} />
                  {doc.name}
                </button>
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
