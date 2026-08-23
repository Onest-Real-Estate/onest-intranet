import { Head, Link, usePage } from "@inertiajs/react";
import { ArrowRight, ChartColumn, CircleAlert } from "lucide-react";

import {
  EmptyState,
  PageHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { Badge } from "@/components/ui/badge";
import { routes } from "@/lib/routes";
import type { ReportCatalogItem, ReportsPageProps } from "@/types";

function ReportCard({ report }: { report: ReportCatalogItem }) {
  return (
    <li>
      <Link
        href={routes.report_detail(report.key)}
        className="border-border hover:bg-muted/40 focus-visible:ring-ring grid gap-2 rounded-lg border p-4 transition-colors focus-visible:ring-2 focus-visible:outline-none"
      >
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-foreground text-base font-semibold">{report.title}</h2>
          {!report.available ? <Badge variant="secondary">Unavailable</Badge> : null}
          <Badge variant="outline">{report.category}</Badge>
        </div>
        <p className="text-muted-foreground text-sm">{report.description}</p>
        <p className="text-muted-foreground text-xs">
          Scope: {report.scope.label} · Calculation v{report.calculationVersion}
        </p>
        <span className="text-primary inline-flex items-center gap-1 text-sm font-medium">
          Open report
          <ArrowRight className="size-4" aria-hidden />
        </span>
      </Link>
    </li>
  );
}

export default function Reports() {
  const { reports, scope, timezone, currency } = usePage<ReportsPageProps>().props;

  return (
    <PermissionRequired permission={{ all: ["web.view_reports"] }}>
      <Head title="Reports" />
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-6 sm:px-6">
        <PageHeader
          title="Reports"
          description={`Role-appropriate operational reports in ${scope.label}. Timezone ${timezone}; currency ${currency}.`}
        />
        {reports.length === 0 ? (
          <EmptyState
            icon={CircleAlert}
            title="No reports in your scope"
            description="You do not currently hold permissions for any registered report."
          />
        ) : (
          <SurfaceCard>
            <SurfaceCardContent className="grid gap-4">
              <div className="flex items-center gap-2">
                <ChartColumn className="text-muted-foreground size-5" aria-hidden />
                <h2 className="text-foreground text-sm font-semibold tracking-wide uppercase">
                  Catalog
                </h2>
              </div>
              <ul className="grid gap-3">
                {reports.map((report) => (
                  <ReportCard key={report.key} report={report} />
                ))}
              </ul>
            </SurfaceCardContent>
          </SurfaceCard>
        )}
      </div>
    </PermissionRequired>
  );
}

Reports.layout = (page: React.ReactNode) => <HubLayout>{page}</HubLayout>;
