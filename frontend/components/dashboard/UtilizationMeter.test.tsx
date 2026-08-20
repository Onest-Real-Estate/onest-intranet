import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axe } from "vitest-axe";

import { UtilizationMeter } from "@/components/dashboard/UtilizationMeter";
import type { DashboardMeter } from "@/types";

const meter: DashboardMeter = {
  headline: "64%",
  caption: "Booked room-minutes over published open hours",
  series: [
    { label: "Conference room", ratio: 0.82 },
    { label: "Closing room", ratio: 0 },
    { label: "Podcast studio", ratio: null },
    { label: "Training room", ratio: 1.2 },
  ],
};

describe("UtilizationMeter", () => {
  it("distinguishes an unmeasured room from an unused one", () => {
    render(<UtilizationMeter title="Room utilization" data={meter} />);

    expect(
      screen.getByLabelText("Closing room: 0%"),
      "a room nobody booked is 0%",
    ).toBeVisible();
    expect(
      screen.getByLabelText("Podcast studio: Not measured"),
      "a room with no open hours has no denominator to divide by",
    ).toBeVisible();
  });

  it("reports over-subscription rather than clamping it away", () => {
    render(<UtilizationMeter title="Room utilization" data={meter} />);

    // Double-booking is a finding, not an artefact — the label keeps the real
    // figure even though the bar cannot draw past its own width.
    expect(screen.getByText("120%")).toBeVisible();
  });

  it("has no detectable accessibility violations", async () => {
    const { container } = render(
      <UtilizationMeter title="Room utilization" data={meter} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
