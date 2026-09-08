import type { ReportSeriesPoint } from "@/types";

interface ReportChartProps {
  title: string;
  series: ReportSeriesPoint[];
  chartKind: "bar" | "none";
  maxValue: number;
}

/**
 * Accessible chart with a mandatory tabular equivalent.
 *
 * Visual bars are decorative; the table is the semantic source of truth for
 * screen readers and keyboard users.
 */
export function ReportChart({ title, series, chartKind, maxValue }: ReportChartProps) {
  if (chartKind === "none" || series.length === 0) {
    return (
      <div
        className="border-border bg-muted/20 text-muted-foreground rounded-lg border p-4 text-sm"
        role="status"
      >
        No chart for this report. Use the detail table below.
      </div>
    );
  }

  const allZero = series.every((point) => Number(point.value) === 0);

  return (
    <figure className="border-border grid gap-4 rounded-lg border p-4">
      <figcaption className="text-foreground text-sm font-semibold">{title}</figcaption>
      {allZero ? (
        <p className="text-muted-foreground text-sm" role="status">
          All series values are zero for the current filters.
        </p>
      ) : null}
      <ul className="grid gap-3" aria-hidden="true">
        {series.map((point) => {
          const width =
            maxValue <= 0
              ? 0
              : Math.max(0, Math.round((Number(point.value) / maxValue) * 100));
          return (
            <li key={point.key} className="grid gap-1">
              <div className="flex items-baseline justify-between gap-2 text-sm">
                <span className="text-foreground">{point.label}</span>
                <span className="text-muted-foreground tabular-nums">
                  {point.value}
                </span>
              </div>
              <div className="bg-muted h-2 overflow-hidden rounded">
                <div
                  className="bg-primary h-full rounded"
                  style={{ width: `${width}%` }}
                />
              </div>
            </li>
          );
        })}
      </ul>
      <table className="w-full border-collapse text-left text-sm">
        <caption className="sr-only">
          Tabular equivalent of {title}. Values match the visual bars.
        </caption>
        <thead>
          <tr className="border-border border-b">
            <th scope="col" className="text-muted-foreground py-2 font-medium">
              Series
            </th>
            <th scope="col" className="text-muted-foreground py-2 font-medium">
              Value
            </th>
          </tr>
        </thead>
        <tbody>
          {series.map((point) => (
            <tr key={point.key} className="border-border border-b last:border-0">
              <td className="py-2">{point.label}</td>
              <td className="py-2 tabular-nums">{point.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
