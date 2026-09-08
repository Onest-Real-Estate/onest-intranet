import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axe } from "vitest-axe";

import { TrainingResources } from "@/components/dashboard/TrainingResources";

const training = {
  percent: 64,
  label: "12 of 18 continuing education hours complete",
  resourceTitle: "Virginia contract forms",
  resourceHint: "Review the updated forms before your next listing appointment.",
};

describe("TrainingResources", () => {
  it("groups progress and the featured resource in one coherent panel", () => {
    render(<TrainingResources training={training} />);

    expect(
      screen.getByRole("heading", { level: 2, name: "Training & resources" }),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { level: 3, name: "Continuing education" }),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { level: 3, name: "Featured resource" }),
    ).toBeVisible();
    expect(screen.getByRole("img", { name: "64 percent complete" })).toBeVisible();
  });

  it("has no detectable accessibility violations", async () => {
    const { container } = render(<TrainingResources training={training} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
