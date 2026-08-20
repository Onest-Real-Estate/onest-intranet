import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axe } from "vitest-axe";

import { HierarchyBreadcrumb } from "@/components/design-system/hierarchy-breadcrumb";

describe("HierarchyBreadcrumb", () => {
  it("renders the root-to-leaf path and marks inactive nodes", () => {
    render(
      <HierarchyBreadcrumb
        segments={[
          { id: 1, name: "Onest Real Estate" },
          { id: 2, name: "Mid-Atlantic" },
          { id: 3, name: "Legacy Branch", isActive: false },
        ]}
      />,
    );

    expect(
      screen.getByRole("navigation", { name: "Organization hierarchy" }),
    ).toBeVisible();
    expect(screen.getByText("Onest Real Estate")).toBeVisible();
    expect(screen.getByText("Legacy Branch")).toHaveAttribute(
      "aria-current",
      "location",
    );
    expect(screen.getByText("Inactive")).toBeVisible();
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(
      <HierarchyBreadcrumb
        segments={[
          { id: 1, name: "Onest Real Estate" },
          { id: 2, name: "Fairfax VA" },
        ]}
      />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
