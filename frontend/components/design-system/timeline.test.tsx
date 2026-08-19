import { render, screen } from "@testing-library/react";
import { CircleCheck } from "lucide-react";
import { describe, expect, it } from "vitest";
import { axe } from "vitest-axe";

import { Timeline } from "@/components/design-system/timeline";

const items = [
  { id: "a", title: "Team training", description: "Conference Room B", meta: "10:00" },
  { id: "b", title: "Client consultation", meta: "13:30", current: true },
];

describe("Timeline", () => {
  it("marks the current step and defaults to a dot rather than a check", () => {
    const { container } = render(<Timeline items={items} />);

    const steps = container.querySelectorAll("li");
    expect(steps).toHaveLength(2);
    expect(steps[1]).toHaveAttribute("aria-current", "step");
    // A check on every entry would claim completion the data does not support.
    expect(container.querySelector("svg")).toBeNull();
  });

  it("renders a per-item icon when one carries meaning", () => {
    const { container } = render(
      <Timeline items={[{ ...items[0], icon: CircleCheck }]} />,
    );
    expect(container.querySelector("svg")).not.toBeNull();
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(<Timeline items={items} />);
    expect(screen.getByText("Team training")).toBeVisible();
    expect(await axe(container)).toHaveNoViolations();
  });
});
