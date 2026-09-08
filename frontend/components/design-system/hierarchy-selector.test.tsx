import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";

import { HierarchySelector } from "@/components/design-system/hierarchy-selector";

const groups = [
  {
    label: "Mid-Atlantic",
    offices: [
      { id: 7, name: "Fairfax VA", pathLabel: "Mid-Atlantic / Fairfax VA" },
      {
        id: 8,
        name: "Closed Desk",
        pathLabel: "Mid-Atlantic / Closed Desk",
        isActive: false,
      },
    ],
  },
  {
    label: "New England",
    offices: [{ id: 9, name: "Connecticut", pathLabel: "New England / Connecticut" }],
  },
];

describe("HierarchySelector", () => {
  const validation = { fields: {}, form: [] as string[] };

  it("filters offices by search query", async () => {
    const user = userEvent.setup();
    render(
      <HierarchySelector
        name="office"
        label="Office"
        value=""
        onChange={vi.fn()}
        groups={groups}
        validation={validation}
      />,
    );

    await user.type(
      screen.getByRole("searchbox", { name: "Search offices or regions" }),
      "Fairfax",
    );
    await user.click(screen.getByRole("combobox"));

    expect(
      await screen.findByRole("option", { name: /Mid-Atlantic \/ Fairfax VA/i }),
    ).toBeVisible();
    expect(
      screen.queryByRole("option", { name: /New England \/ Connecticut/i }),
    ).toBeNull();
  });

  it("disables inactive offices in the open list", async () => {
    const user = userEvent.setup();
    render(
      <HierarchySelector
        name="office"
        label="Office"
        value=""
        onChange={vi.fn()}
        groups={groups}
        validation={validation}
      />,
    );

    await user.click(screen.getByRole("combobox"));
    const inactive = await screen.findByRole("option", { name: /Closed Desk/i });
    expect(inactive).toHaveAttribute("aria-disabled", "true");
  });

  it("has no automated accessibility violations", async () => {
    const { container } = render(
      <HierarchySelector
        name="office"
        label="Office"
        value="7"
        onChange={() => undefined}
        groups={groups}
        validation={validation}
      />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
