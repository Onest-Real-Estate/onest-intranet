import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ReportChart } from "@/components/reporting/ReportChart";

describe("ReportChart", () => {
  it("renders a tabular equivalent for the visual bars", () => {
    render(
      <ReportChart
        title="Onboarding progress chart"
        chartKind="bar"
        maxValue={10}
        series={[
          { key: "ready", label: "Ready", value: 4 },
          { key: "blocked", label: "Blocked", value: 0 },
        ]}
      />,
    );
    expect(screen.getAllByText("Ready").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("4").length).toBeGreaterThanOrEqual(1);
    expect(
      screen.getByRole("table", {
        name: /tabular equivalent of onboarding progress chart/i,
      }),
    ).toBeInTheDocument();
  });

  it("announces an all-zero series", () => {
    render(
      <ReportChart
        title="Empty chart"
        chartKind="bar"
        maxValue={0}
        series={[{ key: "a", label: "A", value: 0 }]}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/all series values are zero/i);
  });

  it("shows a no-chart status when chart kind is none", () => {
    render(<ReportChart title="Pending" chartKind="none" maxValue={0} series={[]} />);
    expect(screen.getByRole("status")).toHaveTextContent(/no chart for this report/i);
  });
});
