import { ChevronRight } from "lucide-react";

import { StatusBadge } from "@/components/design-system/status-badge";
import { cn } from "@/lib/utils";

export type HierarchyBreadcrumbSegment = {
  id: number | string;
  name: string;
  kind?: string;
  isActive?: boolean;
};

/**
 * Root → leaf organizational path for admin and detail screens.
 * Inactive or transitional nodes are labeled, never hidden.
 */
export function HierarchyBreadcrumb({
  segments,
  className,
}: {
  segments: HierarchyBreadcrumbSegment[];
  className?: string;
}) {
  if (segments.length === 0) {
    return null;
  }

  return (
    <nav aria-label="Organization hierarchy" className={cn("text-sm", className)}>
      <ol className="flex flex-wrap items-center gap-x-1 gap-y-1">
        {segments.map((segment, index) => {
          const current = index === segments.length - 1;
          return (
            <li key={String(segment.id)} className="flex items-center gap-1">
              {index > 0 ? (
                <ChevronRight
                  className="text-muted-foreground size-3.5 shrink-0"
                  aria-hidden
                />
              ) : null}
              <span
                className={cn(
                  "text-foreground",
                  !current && "text-muted-foreground",
                  current && "font-medium",
                )}
                aria-current={current ? "location" : undefined}
              >
                {segment.name}
              </span>
              {segment.isActive === false ? (
                <StatusBadge status={{ label: "Inactive", tone: "neutral" }} />
              ) : null}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
