import { Head, Link, usePage } from "@inertiajs/react";
import { ArrowLeft, CircleAlert, Download, LoaderCircle } from "lucide-react";
import { useState } from "react";

import {
  EmptyState,
  FilterControls,
  FilterField,
  PageHeader,
  SurfaceCard,
  SurfaceCardContent,
} from "@/components/design-system";
import { HubLayout } from "@/components/HubLayout";
import { PermissionRequired } from "@/components/PermissionRequired";
import { ReportChart } from "@/components/reporting/ReportChart";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { buildListUrl, visitListUrl } from "@/lib/list-query";
import { routes } from "@/lib/routes";
import type { ReportDetailPageProps, ReportExportJobPayload } from "@/types";

const ALL = "__all__";

function cellValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

export default function ReportDetail() {
  const { report } = usePage<ReportDetailPageProps>().props;
  const [filters, setFilters] = useState(report.appliedFilters);
  const [exportState, setExportState] = useState<ReportExportJobPayload | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  function applyFilters(next: Record<string, string>) {
    setFilters(next);
    visitListUrl(
      buildListUrl(routes.report_detail(report.key), window.location.search, {
        filters: next,
      }),
    );
  }

  function requestExport() {
    setExporting(true);
    setExportError(null);
    void fetch(routes.report_export_create(report.key), {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-XSRF-TOKEN":
          document.cookie
            .split("; ")
            .find((row) => row.startsWith("XSRF-TOKEN="))
            ?.split("=")[1]
            ?.replace(/%([0-9A-F]{2})/gi, (_, hex) =>
              String.fromCharCode(Number.parseInt(hex, 16)),
            ) ?? "",
      },
      body: new URLSearchParams({ format: "csv", ...filters }).toString(),
      credentials: "same-origin",
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error("Export request failed");
        }
        const payload = (await response.json()) as {
          export: ReportExportJobPayload;
        };
        setExportState(payload.export);
        if (payload.export.status === "queued" || payload.export.status === "running") {
          pollExport(payload.export.id);
        }
      })
      .catch(() => setExportError("Export could not be started."))
      .finally(() => setExporting(false));
  }

  function pollExport(jobId: number) {
    window.setTimeout(() => {
      void fetch(routes.report_export_status(jobId), {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      })
        .then(async (response) => {
          if (!response.ok) return;
          const payload = (await response.json()) as {
            export: ReportExportJobPayload;
          };
          setExportState(payload.export);
          if (
            payload.export.status === "queued" ||
            payload.export.status === "running"
          ) {
            pollExport(jobId);
          }
        })
        .catch(() => undefined);
    }, 1200);
  }

  const hasRows = report.rows.length > 0;
  const maxSeries = Math.max(1, ...report.series.map((point) => Number(point.value)));

  return (
    <PermissionRequired permission={{ all: ["web.view_reports"] }}>
      <Head title={report.title} />
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-6 sm:px-6">
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="ghost" size="sm" asChild>
            <Link href={routes.report_catalog()}>
              <ArrowLeft className="size-4" aria-hidden />
              All reports
            </Link>
          </Button>
        </div>
        <PageHeader
          title={report.title}
          description={`${report.description} Scope: ${report.scope.label}.`}
          actions={
            report.canExport && report.available ? (
              <Button type="button" onClick={requestExport} disabled={exporting}>
                {exporting ? (
                  <LoaderCircle className="size-4 animate-spin" aria-hidden />
                ) : (
                  <Download className="size-4" aria-hidden />
                )}
                Export CSV
              </Button>
            ) : null
          }
        />

        <p className="text-muted-foreground text-sm">
          As of {report.dataAsOf ?? report.generatedAt} · Calculation v
          {report.calculationVersion} · {report.timezone} · {report.currency}
        </p>
        {report.comparisonNote ? (
          <p className="text-muted-foreground text-sm">{report.comparisonNote}</p>
        ) : null}
        {report.aggregates.truncated ? (
          <p className="text-muted-foreground text-sm" role="status">
            Showing the first {String(report.syncRowLimit)} rows on this page. Export
            CSV for the full scoped result.
          </p>
        ) : null}
        {exportError ? (
          <p className="text-destructive text-sm" role="alert">
            {exportError}
          </p>
        ) : null}
        {exportState ? (
          <p className="text-muted-foreground text-sm" aria-live="polite">
            Export {exportState.status}
            {exportState.downloadReady ? (
              <>
                {" · "}
                <a
                  className="text-primary underline"
                  href={routes.report_export_download(exportState.id)}
                >
                  Download
                </a>
              </>
            ) : null}
            {exportState.errorMessage ? ` — ${exportState.errorMessage}` : null}
          </p>
        ) : null}

        {!report.available ? (
          <EmptyState
            icon={CircleAlert}
            title="Source not connected"
            description={
              report.emptyReason ??
              "This report's source domain is not connected to the hub yet."
            }
          />
        ) : (
          <>
            {report.filters.length > 0 ? (
              <FilterControls>
                {report.filters.map((field) =>
                  field.kind === "select" ? (
                    <FilterField key={field.key} label={field.label}>
                      <Select
                        value={filters[field.key] || ALL}
                        onValueChange={(next) =>
                          applyFilters({
                            ...filters,
                            [field.key]: next === ALL ? "" : next,
                          })
                        }
                      >
                        <SelectTrigger
                          aria-label={field.label}
                          className="w-full sm:w-44"
                        >
                          <SelectValue
                            placeholder={`All ${field.label.toLowerCase()}`}
                          />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={ALL}>
                            All {field.label.toLowerCase()}
                          </SelectItem>
                          {field.options.map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {option.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </FilterField>
                  ) : (
                    <FilterField key={field.key} label={field.label}>
                      <input
                        className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm sm:w-44"
                        aria-label={field.label}
                        value={filters[field.key] ?? ""}
                        onChange={(event) =>
                          setFilters({
                            ...filters,
                            [field.key]: event.target.value,
                          })
                        }
                        onBlur={() => applyFilters(filters)}
                      />
                    </FilterField>
                  ),
                )}
              </FilterControls>
            ) : null}

            {!hasRows ? (
              <EmptyState
                icon={CircleAlert}
                title="No data"
                description={
                  report.emptyReason ?? "Nothing matched these filters in your scope."
                }
              />
            ) : (
              <>
                <ReportChart
                  title={`${report.title} chart`}
                  series={report.series}
                  chartKind={report.chartKind}
                  maxValue={maxSeries}
                />
                <SurfaceCard>
                  <SurfaceCardContent className="overflow-x-auto">
                    <table className="w-full min-w-[40rem] border-collapse text-left text-sm">
                      <caption className="sr-only">
                        Detail rows for {report.title}. Totals reconcile with the chart
                        under the report calculation rules.
                      </caption>
                      <thead>
                        <tr className="border-border border-b">
                          {report.columns.map((column) => (
                            <th
                              key={column.key}
                              scope="col"
                              className="text-muted-foreground px-2 py-2 font-medium"
                            >
                              {column.label}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {report.rows.map((row) => {
                          const rowKey = report.columns
                            .map(
                              (column) =>
                                `${column.key}:${String(row[column.key] ?? "")}`,
                            )
                            .join("|");
                          return (
                            <tr
                              key={rowKey}
                              className="border-border border-b last:border-0"
                            >
                              {report.columns.map((column) => (
                                <td key={column.key} className="px-2 py-2">
                                  {cellValue(row[column.key])}
                                </td>
                              ))}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </SurfaceCardContent>
                </SurfaceCard>
              </>
            )}
          </>
        )}
      </div>
    </PermissionRequired>
  );
}

ReportDetail.layout = (page: React.ReactNode) => <HubLayout>{page}</HubLayout>;
